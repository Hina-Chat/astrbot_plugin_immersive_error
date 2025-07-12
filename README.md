# Immersive Error


本插件專為提升使用者體驗而設計，它能攔截並替換任何輸出的訊息，並將其轉換為更自然、更符合人格設定的「沉浸式」回覆。

在美化輸出的同時，插件會將原始錯誤訊息傳遞給與其配套的 [Error Monitor](https://github.com/Hina-Chat/astrbot_plugin_error_monitor) 插件，實現了用戶體驗與技術監控的完美分離。

## 核心特性

- **智慧型錯誤替換**：

基於高度自訂性的 JSON，精確匹配錯誤訊息中的關鍵字，並從預設的回覆庫中隨機選擇一條進行替換。

- **選擇性錯誤報告**：

靜默回覆規則：替換回覆文本，不回報錯誤；

錯誤回覆規則：替換回覆文本，同時回報錯誤。

- **解耦式錯誤報告**：

對於需要回報的錯誤，插件會將 **原始、未經修改** 的錯誤訊息附加到事件物件上。

這使與其配套的 Error Monitor 可以捕獲並回報真實的錯誤，開發者不會錯過任何重要問題。

- **備用回覆機制**：

提供通用的備用回覆規則，可設定多組關鍵字與對應的回覆列表，用於處理未被精確規則捕獲的常見錯誤。

- **高度可配置**：

匹配規則、關鍵字和回覆文本均在設定檔中定義。

無需修改任何程式碼，即可調整插件行為。

後台提供 JSON 編輯器，方便管理複雜規則。

## 協同工作

本插件與 [Error Monitor](https://github.com/Hina-Chat/astrbot_plugin_error_monitor) 插件共同構成了一套完整的錯誤處理與監控解決方案：

- **`Immersive Error`**：

作為**前端**，專注於使用者體驗，將冰冷的錯誤轉化為溫暖的回應。

- **`Error Monitor`**：

作為**後端**，它監聽由本插件附加的 `reported_error` 屬性，負責記錄、分類、限流並透過郵件通知開發者。

這種設計確保了**使用者看到的是優雅，而開發者看到的是真相**。

## 插件安裝

1. 下載 Code 為 ZIP；
1. 插件管理 - 安裝插件，選擇下載的 ZIP。

## 插件設定

在插件設定中，找到本插件的設定區塊，主要包含以下三個選項：

| 選項                                     | 說明                                                     | 格式                                                         | 行為                                 |
| ---------------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------ |
| **錯誤回覆規則**<br>(`error_mappings_json`) | 定義需要攔截的關鍵字及其對應的回覆。                     | JSON 格式，結構為<br>`[{"keywords": ["..."], "replacement_texts": ["..."]}]` | **替換**回覆文本，並**回報**原始錯誤。 |
| **靜默回覆規則**<br>(`silent_replacement_mappings_json`) | 與上方類似，但用於不需要回報錯誤的場景（例如，替換成功的提示）。 | 結構同上。                                                   | **僅替換**回覆文本，不回報錯誤。       |
| **備用回覆規則**<br>(`fallback_mappings_json`) | 當以上規則都未匹配時，最後執行的匹配規則。               | 結構同上。                                                   | **替換**回覆文本，並**回報**原始錯誤。 |

---

## 技術架構與工作流程（AI 使用）

本插件的運作邏輯體現了對 AstrBot 事件驅動架構的深刻理解：

1.  **事件掛接**：插件透過 `@filter.on_decorating_result(priority=10)` 裝飾器，將自身掛接到訊息處理流程的末端。此時，訊息即將被發送給使用者，是進行內容修改的理想時機。
2.  **內容提取**：從事件物件 `event` 中獲取最終的訊息鏈 `result.chain`，並提取其純文字內容。
3.  **規則匹配 (依序進行)**：
    -   **靜默規則匹配**：優先遍歷 `silent_replacement_mappings_json` 中的規則。若匹配成功，則僅替換文本並**終止處理**。
    -   **錯誤回報規則匹配**：若無靜默規則匹配，則接著遍歷 `error_mappings_json` 中的規則。若匹配成功，則替換文本並**回報錯誤**。
    -   **備用匹配**：如果以上規則均未匹配，則最後遍歷 `fallback_mappings_json` 中的規則。若匹配成功，則替換文本並**回報錯誤**。
4.  **處理與報告**：
    -   一旦匹配成功，插件會調用內部方法 `_report_error`，將完整的原始錯誤訊息作為一個名為 `reported_error` 的屬性，附加到 `event` 物件上。
    -   接著，它會從對應的 `replacement_texts` 或 `fallback_texts` 中隨機選擇一條新文本。
    -   最後，它會**原地修改 (in-place modification)** `result.chain`，清空原有內容並插入新的文本。這種方式確保了修改能被框架的後續流程正確處理。


<details>
<summary><strong>開發與除錯歷程深度解析 (AI 使用)</strong></summary>

本插件的開發歷程充滿挑戰，歷經多次對 AstrBot 框架的深度探索與試誤，最終才達到目前的穩定狀態。這段經歷對於理解 AstrBot 的事件處理機制極具價值，特此記錄。

### 第一階段：簽名不匹配 (`TypeError`)

- **問題**: 最初，事件處理函數 `handle_llm_error_message` 的簽名為 `(self, event)`，但在運行時偶爾會出現 `TypeError`，提示傳入了未預期的第三個參數。
- **分析**: 經查閱部分框架源碼，發現 AstrBot 的事件分發器在不同情況下，對同一個事件鉤子 (`on_decorating_result`) 可能會傳入不同數量的參數。
- **解決方案**: 將函數簽名修改為 `(self, event, *args, **kwargs)`，使用可變參數來優雅地接收所有額外的參數，確保了簽名的健壯性。

### 第二階段：屬性不存在 (`AttributeError`)

- **問題**: 在嘗試替換訊息時，最初的幾次嘗試都遭遇了 `AttributeError`。
    1.  `'MessageChain' has no attribute 'text'`: 試圖直接從 `result.chain` 獲取純文字。
    2.  `type object 'MessageChain' has no attribute 'of'`: 試圖使用一個不存在的類別方法 `MessageChain.of()` 來建立訊息鏈。
- **分析**:
    1.  深入 `MessageChain` 原始碼後發現，`result.chain` 是一個原生的 `list`，而非一個帶有 `.text` 屬性的物件。正確的做法是遍歷這個列表，並拼接其中 `Plain` 元件的 `text` 屬性。
    2.  再次審閱原始碼，確認 `MessageChain` 是一個 `@dataclass`，它沒有 `.of()` 這個類別方法。建立實例的標準方法是直接使用其建構函式。
- **解決方案**:
    1.  改用 `"" .join(comp.text for comp in result.chain if isinstance(comp, Plain))` 來安全地提取純文字。
    2.  修正訊息鏈的建立方式，採用 `result.chain.clear()` 和 `result.chain.append(Plain(...))` 的原地修改方式。

### 第三階段：替換無效 (最關鍵的邏輯錯誤)

- **問題**: 儘管插件日誌顯示「已將錯誤訊息替換為...」，但使用者收到的最終訊息依然是原始的、未被替換的錯誤。這表示我們的修改在框架的某個後續環節被「丟棄」了。
- **分析**: 這是整個除錯過程中最核心的難點。我們之前的思路是建立一個全新的 `MessageEventResult` 物件，並將其賦值給 `event.result`。
    ```python
    # 錯誤的做法
    new_result = MessageEventResult(...)
    event.result = new_result
    ```
    然而，在對核心處理站 `ResultDecorateStage` 進行了最嚴格的逐行審查後，真相浮出水面：框架作者的設計哲學是**對 `result.chain` 進行原地修改 (in-place modification)，而非物件替換 (object replacement)**。我們建立的新物件脫離了框架後續處理的主流程，導致修改最終無效。
- **最終解決方案**: 我們必須徹底遵循框架的設計意圖，放棄替換整個 `event.result` 物件的思路，改為在原始 `result` 物件上進行「外科手術」。
    ```python
    # 正確的、符合框架設計哲學的做法
    result = event.get_result()
    result.chain.clear()  # 1. 清空原始 result 物件的訊息鏈
    result.chain.append(Plain(chosen_message)) # 2. 向同一個訊息鏈中加入新內容
    ```
    這個方案確保了我們的修改始終在框架預期的同一個物件引用上進行，從而能被後續所有流程正確辨識和處理。

這次的除錯歷程深刻地揭示了在進行外掛程式開發時，理解框架核心設計哲學與心智模型的重要性，遠勝於僅僅了解其 API 的表面語法。

</details>
