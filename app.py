from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import requests
import os
import json

app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ✅ 跨域设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # 如果你在本地跑前端
        "https://your-project-name.vercel.app"  # ✅ 替换为你真实部署到 Vercel 的前端域名
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# ✅ 获取环境变量中的 API Key
UNSPLASH_API_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# ✅ 首页测试
@app.get("/")
def root():
    return {"message": "BioQuest backend is running on Render"}

# ✅ 获取图片接口
@app.get("/image")
def get_image(topic: str = Query(...)):
    headers = {"Authorization": f"Client-ID {UNSPLASH_API_KEY}"}
    res = requests.get(f"https://api.unsplash.com/search/photos?query={topic}&per_page=1", headers=headers)
    data = res.json()
    url = data["results"][0]["urls"]["regular"] if data["results"] else ""
    return JSONResponse({"url": url})

# ✅ 获取视频接口
@app.get("/video")
def get_video(topic: str = Query(...)):
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={topic}&key={YOUTUBE_API_KEY}&type=video&maxResults=1"
    res = requests.get(url)
    data = res.json()
    if "items" in data and data["items"]:
        video_id = data["items"][0]["id"]["videoId"]
        return JSONResponse({"url": f"https://www.youtube.com/watch?v={video_id}"})
    return JSONResponse({"url": ""})

# ✅ 学生端 AI 聊天接口
class ChatRequest(BaseModel):
    message: str
    history: list

@app.post("/chat")
def chat(request: ChatRequest):
    system_prompt = {
        "role": "system",
        "content": (
            "You are a friendly biology tutor who explains complex terms using simple everyday language, "
            "avoids jargon, and breaks answers into short, readable pieces. "
            "Always end with a gentle, open-ended guiding question to encourage further thinking."
        ),
    }

    messages = [system_prompt] + request.history + [{"role": "user", "content": request.message}]
    try:
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        reply = res.choices[0].message.content
        return JSONResponse({"reply": reply})
    except Exception as e:
        return JSONResponse({"reply": f"Error: {str(e)}"})

# ✅ 教师端 AI 聊天接口
class TeacherChatRequest(BaseModel):
    message: str
    history: list

@app.post("/teacher-chat")
def teacher_chat(request: TeacherChatRequest):
    system_prompt = {
        "role": "system",
        "content": (
            "You are a professional biology curriculum designer. "
            "Your goal is to help teachers create effective, well-organized lesson plans. "
            "Always format your response clearly using bullet points, numbered sections, or markdown tables. "
            "If the user's request lacks details such as student grade level, lesson duration, or learning goals, "
            "generate a basic draft **but also politely ask follow-up questions** to clarify the missing context. "
            "Avoid casual tone and do not use emojis. "
            "Use markdown to make content easy to read in HTML rendering (e.g. `**bold**`, tables, headers)."
        )
    }

    try:
        # ✅ 自动裁剪 history，只保留最近 4 条（2轮对话）
        trimmed_history = request.history[-4:] if len(request.history) > 4 else request.history

        chat_messages = [system_prompt]
        for entry in trimmed_history:
            if isinstance(entry, str) and ": " in entry:
                role, content = entry.split(": ", 1)
                chat_messages.append({"role": role.strip(), "content": content.strip()})

        # ✅ 添加当前用户请求
        chat_messages.append({"role": "user", "content": request.message})

        # ✅ 发起 GPT 请求
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=chat_messages,
            temperature=0.7,
        )

        reply = res.choices[0].message.content
        return JSONResponse({"reply": reply})

    except Exception as e:
        print("❌ OpenAI request error:", str(e))  # ✅ 打印到服务器日志
        return JSONResponse(
            status_code=500,
            content={"reply": f"Error occurred in lesson generation: {str(e)}"}
        )

# ✅ 生成 Quiz 接口
@app.post("/quiz")
async def generate_quiz(request: Request):
    data = await request.json()
    topic = data.get("topic", "biology")
    prompt = f"""Generate a 3-question multiple choice quiz on {topic}.
Each question should have:
- A question
- 4 options
- The correct answer
- A short explanation.
Format the output as a JSON list like this:
[
  {{
    "question": "...",
    "options": ["A", "B", "C", "D"],
    "answer": "...",
    "explanation": "..."
  }},
  ...
]"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        result_text = response.choices[0].message.content.strip()
        questions = json.loads(result_text)
        return JSONResponse(content={"questions": questions})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

