import secrets
import random
import json
import asyncio

from astrbot.api.event import (
    filter,
    AstrMessageEvent,
)
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Plain


class ImmersiveErrorPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.load_task = None  # 用於追蹤加載任務

        # 先初始化為空，避免在異步加載完成前被調用而出錯
        self.error_mappings = []
        self.silent_mappings = []
        self.fallback_mappings = []

        # 創建一個異步任務來加載配置
        self.load_task = asyncio.create_task(self._initialize())

        # 讀取延時配置
        self.delay_enabled = self.config.get("delay_enabled", False)
        self.delay_min = self.config.get("delay_min_seconds", 1.0)
        self.delay_max = self.config.get("delay_max_seconds", 3.0)

    async def _initialize(self):
        """異步加載規則。"""
        logger.info("ImmersiveErrorPlugin 正在異步加載規則...")
        self.error_mappings = await self._load_json_rules("error_mappings_json")
        self.silent_mappings = await self._load_json_rules(
            "silent_replacement_mappings_json"
        )
        self.fallback_mappings = await self._load_json_rules("fallback_mappings_json")

        log_message = (
            f"沉浸式錯誤處理插件已載入。成功加載 "
            f"{len(self.error_mappings)} 條錯誤規則，"
            f"{len(self.silent_mappings)} 條靜默規則，"
            f"{len(self.fallback_mappings)} 條備用規則。"
        )
        logger.info(log_message)

    async def _load_json_rules(self, config_key: str) -> list:
        """從設定中異步讀取並解析 JSON 規則，避免阻塞。"""
        json_str = self.config.get(config_key, "[]")
        try:
            # 將同步的、可能阻塞的 json.loads 操作放到工作線程中運行
            rules = await asyncio.to_thread(json.loads, json_str)
            if not isinstance(rules, list):
                logger.warning(
                    f"沉浸式錯誤設定中的 '{config_key}' 不是一個有效的列表，將使用空規則。"
                )
                return []
            return rules
        except json.JSONDecodeError:
            logger.error(
                f"沉浸式錯誤設定中的 '{config_key}' 格式錯誤，無法解析，將使用空規則。"
            )
            return []

    async def _report_error(self, event: AstrMessageEvent, error_message: str):
        """通過豐富化 event 對象來報告錯誤"""
        try:
            setattr(event, "reported_error", error_message)
            logger.debug(f"已將錯誤報告附加到事件中: {error_message[:100]}...")
        except Exception as e:
            logger.error(f"附加錯誤報告到事件時發生異常: {e}")

    @filter.on_decorating_result(priority=10)
    async def handle_llm_error_message(self, event: AstrMessageEvent, *args, **kwargs):
        result = event.get_result()
        if not result or not result.chain:
            return

        full_text = "".join(
            item.text for item in result.chain if isinstance(item, Plain)
        )
        if not full_text:
            return

        # 依序應用規則集
        # 1. 靜默規則 (不回報錯誤)
        if await self._apply_rule_set(
            event, full_text, self.silent_mappings, "靜默", report_error=False
        ):
            return

        # 2. 錯誤回報規則
        if await self._apply_rule_set(
            event, full_text, self.error_mappings, "錯誤", report_error=True
        ):
            # 僅在錯誤規則匹配成功後執行延時
            await self._perform_delay()
            return

        # 3. 備用規則 (回報錯誤)
        if await self._apply_rule_set(
            event, full_text, self.fallback_mappings, "備用", report_error=True
        ):
            return

    async def _apply_rule_set(
        self,
        event: AstrMessageEvent,
        full_text: str,
        rules: list,
        rule_type: str,
        report_error: bool,
    ) -> bool:
        """通用規則處理器，返回 True 表示已匹配並處理。"""
        for i, rule in enumerate(rules):
            keywords = rule.get("keywords", [])
            replacement_texts = rule.get("replacement_texts", [])

            if not isinstance(keywords, list) or not isinstance(
                replacement_texts, list
            ):
                logger.warning(
                    f"沉浸式處理：{rule_type}規則索引 {i} 的格式不正確，已跳過。"
                )
                continue

            if not keywords or not replacement_texts:
                continue

            for keyword in keywords:
                if keyword and keyword in full_text:
                    log_message = f"沉浸式處理：{rule_type}規則 {i} (關鍵字: {keyword}) 匹配，訊息已替換。"
                    if report_error:
                        log_message += "，附加原始錯誤以供監控。"
                        await self._report_error(event, full_text)

                    logger.info(log_message)

                    new_text = secrets.choice(replacement_texts)
                    result = event.get_result()
                    result.chain.clear()
                    result.chain.append(Plain(text=new_text))
                    return True  # 匹配成功，終止處理
        return False  # 當前規則集無匹配

    async def _perform_delay(self):
        """如果啟用了延時，則異步等待一段隨機時間，並處理無效設定。"""
        if self.delay_enabled:
            min_delay, max_delay = self.delay_min, self.delay_max

            if min_delay > max_delay:
                logger.warning(
                    f"ImmersiveErrorPlugin: 延時設定錯誤，最小值 ({min_delay}s) 大於最大值 ({max_delay}s)。"
                    f" 將自動交換數值以繼續執行。"
                )
                min_delay, max_delay = max_delay, min_delay  # 自動交換

            # 確保延時時間為正數
            if max_delay > 0:
                # 計算實際延時，確保不為負
                delay_time = random.uniform(max(0, min_delay), max_delay)
                if delay_time > 0:
                    logger.debug(
                        f"ImmersiveErrorPlugin: 觸發延時，將等待 {delay_time:.2f} 秒。"
                    )
                    await asyncio.sleep(delay_time)

    async def terminate(self):
        """插件終止時調用，取消正在進行的加載任務。"""
        if self.load_task and not self.load_task.done():
            self.load_task.cancel()
            logger.info("ImmersiveErrorPlugin: 已取消正在進行的配置加載任務。")
        logger.info("沉浸式錯誤處理插件已卸載。")
