import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from huggingface_hub import InferenceClient
import random
import urllib.parse

app = Flask(__name__)

# --- 基礎設定 ---
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# 初始化 Hugging Face Client
client = InferenceClient(token=os.environ.get("HF_TOKEN"))

manager_id = "XXXXXXXXXXXXXXXXXXXXXX" 
record_file = "selected_res.txt"

def get_tw_time():
    return datetime.utcnow() + timedelta(hours=8)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"Callback Error: {e}", file=sys.stderr)
        abort(400)
    return 'OK'

def update_weight(res_name, feedback_type):
    excel_file = "Available_Restaurant.xlsx"
    # 讀取權重 Sheet
    df_prob = pd.read_excel(excel_file, sheet_name="Probability")
    idx = df_prob[df_prob['Restaurant_Name'] == res_name].index
    
    if not idx.empty:
        if feedback_type == "REJECT":
            df_prob.loc[idx, 'Weight'] *= 0.9  # 拒絕則權重打 9 折
        elif feedback_type == "ACCEPT":
            df_prob.loc[idx, 'Weight'] *= 1.05 # 接受則微增 5%
            
        # 存回 Excel，保持 Sheet2 更新
        with pd.ExcelWriter(excel_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df_prob.to_excel(writer, sheet_name="Probability", index=False)

def pick_restaurant(today_str, weekday_str):
    excel_file = "Available_Restaurant.xlsx"

    df_res = pd.read_excel(excel_file, sheet_name="Available_Restaurant")
    day_key = f"週{weekday_str}" # 確保與 Excel 欄位名稱一致，如 "週三"
    if day_key not in df_res.columns:
        day_key = "週一" # 備援機制
    
    candidates = df_res[day_key].dropna().astype(str).tolist()

    # 2. 從 Sheet2 (Probability) 讀取所有權重
    df_prob = pd.read_excel(excel_file, sheet_name="Probability")

    mask = df_prob['Restaurant_Name'].isin(candidates)
    current_day_probs = df_prob[mask]
    
    res_list = current_day_probs['Restaurant_Name'].tolist()
    weight_list = current_day_probs['Weight'].tolist()
    
    # 執行加權隨機抽選
    if not res_list: # 如果剛好都沒對應到，就從 candidates 隨機選
        selected = random.choice(candidates)
    else:
        selected = random.choices(res_list, weights=weight_list, k=1)[0]

    base_url = "https://huggingface.co/spaces/zuyogoblin/line-order-bot/resolve/main/Menu_Pictures"
    # 使用 quote 處理店名中的特殊字元或中文，避免網址斷掉
    safe_name = urllib.parse.quote(selected)
    menu_url = f"{base_url}/{safe_name}.png"

    
    # AI 判斷節日
    holiday_msg = ""
    try:
        holiday_prompt = f"今天是 {today_str} (週{weekday_str})。請問這是一個特殊的國定假日或節慶嗎？只需回答 [YES]節日名稱 或 [NO]。"
        holiday_res = client.chat.completions.create(model="meta-llama/Llama-3.1-8B-Instruct", messages=[{"role":"user","content":holiday_prompt}], max_tokens=20)
        if "[YES]" in holiday_res.choices[0].message.content:
            holiday_msg = f"\n⚠️ 提醒：今日為特殊節日，請確認營業時間。"
    except: pass

    # 寫入 PENDING
    with open(record_file, "a", encoding="utf-8") as f:
        f.write(f"{selected} {today_str} PENDING\n")

    res_msg = (
        f"🍴 抽選結果：【{selected}】{holiday_msg}\n\n"
        f"📖 菜單傳送門：{menu_url}\n\n"
        f"滿意請點餐，不滿意請說「換一家」。"
    )

    return {
        "name": selected,
        "msg": res_msg
    }

    
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    user_id = event.source.user_id
    tw_time = get_tw_time()
    today_str = tw_time.strftime("%Y.%m.%d")
    weekday_str = ["一", "二", "三", "四", "五", "六", "日"][tw_time.weekday()]

    # 1. 管理員指令：清除
    if user_text == "清除" and user_id == manager_id:
        if os.path.exists(record_file):
            os.remove(record_file)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🧹 紀錄已清除，本周紀錄已重置！"))
        return

    # 2. 核心功能：抽選餐廳
    if user_text == "點餐":
        # 檢查今天是否已經有點餐紀錄 (已鎖定 LOCKED)
        if os.path.exists(record_file):
            with open(record_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines and today_str in lines[-1] and "LOCKED" in lines[-1]:
                    today_res = lines[-1].split(" ")[0]
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎲 今日已鎖定為：【{today_res}】\n請直接輸入餐點內容。"))
                    return

        res_data = pick_restaurant(today_str, weekday_str)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res_data["msg"]))
        return

    # 3. 意圖攔截 (這段必須在「if 點餐」之外，才能處理後續的對話)
    try:
        check_prompt = f"""
            你是一個點餐系統的後端分類器。
            嚴禁聊天！嚴禁解釋！只需根據使用者輸入回覆以下三種標籤之一：
            
            1. 如果使用者不想要這家店、想換一家、不喜歡、換、抽下一家：
               回覆：[CHANGE]
            
            2. 如果使用者「明確說出要點什麼餐點」（包含餐點名稱，可能帶數量）：
               回覆：[YES]餐點名稱x數量 (若無數量則補x1)
               範例：點一個排骨飯 -> [YES]排骨飯x1
               範例：檸檬雞肉堡 -> [YES]檸檬雞肉堡x1
            
            3. 其他無關點餐的閒聊（如：你好、謝謝、你是誰）：
               回覆：[NO]
            
            使用者說："{user_text}"
            回覆標籤："""
        intent_res = client.chat.completions.create(
            model="meta-llama/Llama-3.1-8B-Instruct",
            messages=[{"role": "user", "content": check_prompt}],
            max_tokens=50
        )
        intent_output = intent_res.choices[0].message.content.strip()

        # A. 處理「換一家」
        if "[CHANGE]" in intent_output:
            # 檢查最後一行是否為 PENDING (如果已經 LOCKED 就不能換)
            if os.path.exists(record_file):
                with open(record_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                if lines and today_str in lines[-1]:
                    if "LOCKED" in lines[-1]:
                        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 抱歉，今日已有訂單，無法更換餐廳。"))
                        return
                        
                    rejected_res = lines[-1].split(" ")[0]
                    update_weight(rejected_res, "REJECT")
            
            res_data = pick_restaurant(today_str, weekday_str)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🔄 已調降該店機率，重新抽選：\n{res_data['msg']}"))
            return
            

        # B. 處理「確認點餐」
        if "[YES]" in intent_output:
            order_content = intent_output.replace("[YES]", "").strip()
            
            if os.path.exists(record_file):
                with open(record_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                if lines and today_str in lines[-1]:
                    current_res = lines[-1].split(" ")[0]
                    update_weight(current_res, "ACCEPT")
                    lines[-1] = f"{current_res} {today_str} LOCKED\n"
                    with open(record_file, "w", encoding="utf-8") as f:
                        f.writelines(lines)

                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ 點餐成功：{order_content}"))
                    line_bot_api.push_message(manager_id, TextSendMessage(text=f"🔔 新單：{current_res}\n🍱 內容：{order_content}"))
                    return

    except Exception as e:
        print(f"Logic Error: {e}")

    # 4. 自由對話 (只有以上都不符合時執行)
    try:
        response = client.chat.completions.create(
            model="meta-llama/Llama-3.1-8B-Instruct",
            messages=[{"role": "system", "content": "你是助手。請用一句話簡短回覆。"},
                      {"role": "user", "content": user_text}],
            max_tokens=50
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        print(f"Chat Error: {e}")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=7860)