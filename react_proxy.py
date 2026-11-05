import sys
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import re
import json
import os
import urllib.parse
import html as pyhtml

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API配置
REAL_LLM_URL = "https://api.deepseek.com/chat/completions"
REAL_LLM_API_KEY = ""
REAL_LLM_MODEL = "deepseek-reasoner"
MAX_REACT_ITERATIONS = 5 

# ==========================================
# 【新增】：动态数据库文件名管理器
# ==========================================
def get_db_filename(session_id: str):
    # 清洗未被酒馆解析的宏（比如不在群聊时残留的 {{group}}）
    safe_id = re.sub(r'(\{\{.*?\}\})', '', session_id)
    # 将不能作为文件名的特殊字符替换为下划线，保留中文和英数
    safe_id = re.sub(r'[^a-zA-Z0-9_\-\u4e00-\u9fa5]', '_', safe_id).strip('_')
    if not safe_id:
        safe_id = "default"
    return f"theory_db_{safe_id}.json"

def load_theory_db(session_id: str):
    fname = get_db_filename(session_id)
    if os.path.exists(fname):
        try:
            with open(fname, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_theory_db(data, session_id: str):
    fname = get_db_filename(session_id)
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def execute_tool(action_name: str, query: str) -> str:
    print(f"🔧 [TOOL EXECUTION] {action_name} | {query}")

    if action_name == "SEARCH_WIKI":
        encoded_query = urllib.parse.quote(query.strip())
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&utf8=&format=json"
        headers = {"User-Agent": "EODHCTSiqsxajs/1.1 (Contact: ceftscp@protonmail.com)"}
        
        try:
            resp = httpx.get(url, headers=headers, timeout=10.0)
            if resp.status_code != 200:
                return f"ERROR: Wikipedia API blocked the request (HTTP {resp.status_code})."
                
            resp_json = resp.json()
            results = resp_json.get("query", {}).get("search", [])
            if not results:
                return f"No Wikipedia results found for '{query}'."
            
            res_str = f"Top Wikipedia Results for '{query}':\n"
            for r in results[:3]:
                clean_snippet = re.sub(r'<[^>]+>', '', r['snippet'])
                res_str += f"- Exact Title: [{r['title']}] (Snippet: {clean_snippet}...)\n"
            
            res_str += "\n[SYSTEM: To read the full entry, use ::: ACTION_CALL: READ_WIKI_PAGE | Exact Title :::]"
            return res_str
        except Exception as e:
            return f"ERROR: Wikipedia Search Failed. {str(e)}"

    elif action_name == "READ_WIKI_PAGE":
        encoded_title = urllib.parse.quote(query.strip())
        url = f"https://en.wikipedia.org/w/api.php?format=json&action=query&prop=extracts&exintro=1&explaintext&redirects=1&titles={encoded_title}"
        headers = {"User-Agent": ""}
        
        try:
            resp = httpx.get(url, headers=headers, timeout=10.0)
            if resp.status_code != 200:
                return f"ERROR: Wikipedia API blocked the request (HTTP {resp.status_code})."
                
            resp_json = resp.json()
            pages = resp_json.get("query", {}).get("pages", {})
            
            for page_id, page_data in pages.items():
                if page_id == "-1":
                    return f"ERROR: Wikipedia page '{query}' not found. Try using SEARCH_WIKI first."
                
                extract = page_data.get("extract", "No content available on this page.")
                truncated_extract = extract[:2000] + ("\n...(Content Truncated)..." if len(extract) > 3000 else "")
                return f"FULL TEXT OF '{page_data.get('title')}':\n{truncated_extract}"
                
        except Exception as e:
            return f"ERROR: Wikipedia Page Read Failed. {str(e)}"

    return f"ERROR: Unknown Action '{action_name}'."

async def run_react_loop(req_data: dict):
    turn_events = []
    raw_messages = req_data.get("messages", [])
    messages = []
    session_id = "default"
    
    # ==========================================
    # 【新增】：提取隐藏信标并清洗上下文
    # ==========================================
    for msg in raw_messages:
        content = msg.get("content", "").strip()
        if not content: continue 
        
        # 扫描并提取 SESSION_ID
        match = re.search(r':::\s*SESSION_ID:\s*(.*?)\s*:::', content)
        if match:
            session_id = match.group(1).strip()
            # 从上下文中隐去这行标记，防止大模型产生幻觉去回复它
            content = content.replace(match.group(0), "").strip()
            
        messages.append({"role": msg["role"], "content": content})
    
    # ==========================================
    # 【新增】：智能清空特定档案的数据库
    # ==========================================
    history_msgs_count = sum(1 for m in messages if m["role"] != "system")
    if history_msgs_count <= 2:
        print(f"\n🔄 [SYSTEM DETECT] 检测到全新对话 (信标: {session_id})，正在重置理论数据库...")
        save_theory_db({}, session_id)
        current_theory_db = {}
        turn_events.append(f"🔄 检测到新对话，已自动清空【{session_id}】的理论数据库")
    else:
        current_theory_db = load_theory_db(session_id)
        
    db_injection = f"::: SYSTEM INJECTION :::\nCurrent Cumulative Theory Usage Counts:\n{json.dumps(current_theory_db, ensure_ascii=False, indent=2)}\n\nWARNING: Any theory with a count of 3 or higher is EXHAUSTED and FORBIDDEN. You MUST switch theories if yours is exhausted."
    
    for msg in messages:
        if msg["role"] == "system":
            msg["content"] = msg["content"] + "\n\n" + db_injection
            break

    req_max_tokens = req_data.get("max_tokens", 8192)
    if req_max_tokens <= 0 or req_max_tokens > 8192: req_max_tokens = 8192

    async with httpx.AsyncClient(timeout=120.0) as client:
        for iteration in range(MAX_REACT_ITERATIONS):
            print(f"\n🔄 --- ReAct Iteration {iteration + 1} --- [Session: {session_id}]")
            turn_events.append(f"🔄 ReAct Iteration {iteration + 1} 开始")

            payload = {
                "model": REAL_LLM_MODEL,
                "messages": messages,
                "temperature": req_data.get("temperature", 1.0),
                "max_tokens": req_max_tokens 
            }
            headers = {"Authorization": f"Bearer {REAL_LLM_API_KEY}", "Content-Type": "application/json"}
            
            response = await client.post(REAL_LLM_URL, json=payload, headers=headers)
            if response.status_code != 200:
                print(f"\n❌ [DEEPSEEK API 拒绝了请求] 状态码: {response.status_code}")
                response.raise_for_status()
            
            actual_finish_reason = response.json()["choices"][0].get("finish_reason", "stop")
            message_data = response.json()["choices"][0]["message"]
            
            reasoning = message_data.get("reasoning_content", "")
            llm_reply = message_data.get("content", "")
            full_output = reasoning + "\n" + llm_reply
            
            action_match = re.search(r':::\s*ACTION_CALL:\s*([A-Z_]+)\s*\|\s*(.*?)\s*:::', full_output)

            if action_match:
                action_name = action_match.group(1).strip()
                query = action_match.group(2).strip()
                observation = execute_tool(action_name, query)
                turn_events.append(f"🔧 执行动作: {action_name} | {query}")
                messages.append({"role": "assistant", "content": llm_reply})
                
                remaining_iterations = MAX_REACT_ITERATIONS - iteration - 1
                if remaining_iterations > 1: status_reminder = f" You have {remaining_iterations - 1} tool call(s) remaining."
                elif remaining_iterations == 1: status_reminder = " [CRITICAL WARNING: MAXIMUM TOOL CALLS REACHED. In your next response, you are STRICTLY FORBIDDEN from using ::: ACTION_CALL :::.]"
                else: status_reminder = ""

                observation_prompt = f"::: EODHCTSiqsxajs Database Intercept :::\n[Observation from {action_name}]: {observation}\nAction completed.{status_reminder} Now, continue your <thinking> and output the final narrative."
                messages.append({"role": "user", "content": observation_prompt})
                print(f"👁️  [OBSERVATION FED TO LLM]: {observation}")
                
            else:
                print(f"✅ [FINAL NARRATIVE GENERATED] - Session: {session_id}")
                thought_text = reasoning.strip()
                raw_reply = llm_reply.strip()
                
                thought_match = re.search(r'<thinking>([\s\S]*?)</thinking>', raw_reply)
                if thought_match:
                    thought_text = (thought_text + "\n" + thought_match.group(1).strip()).strip()
                    raw_reply = raw_reply.replace(thought_match.group(0), "").strip()
                
                json_str = ""
                story_text = ""
                
                if "::: EODHCTSiqsxajs Output :::" in raw_reply:
                    parts = raw_reply.split("::: EODHCTSiqsxajs Output :::", 1)
                    json_candidate = parts[0]
                    story_text = parts[1].strip()
                    brace_match = re.search(r'\{[\s\S]*\}', json_candidate)
                    if brace_match: json_str = brace_match.group(0)
                    else: json_str = json_candidate
                else:
                    brace_match = re.search(r'^(\{[\s\S]*?\})\s*(.*)', raw_reply, re.DOTALL)
                    if brace_match:
                        json_str = brace_match.group(1)
                        story_text = brace_match.group(2).strip()
                    else:
                        story_text = raw_reply.strip()

                story_text = re.sub(r'^```[a-z]*\s*', '', story_text)
                story_text = re.sub(r'```$', '', story_text.strip()).strip()
                
                active_theories = []
                if json_str:
                    try:
                        parsed = json.loads(json_str)
                        for key in ["Active_Theories_This_Turn", "Theory_Usage_Log", "Active_Theories"]:
                            if key in parsed:
                                val = parsed[key]
                                if isinstance(val, list): active_theories = val
                                elif isinstance(val, dict): active_theories = list(val.keys())
                                elif isinstance(val, str): active_theories = [val]
                                break
                    except Exception as e:
                        pass
                    
                    if not active_theories:
                        fallback_match = re.search(r'"(?:Active_Theories_This_Turn|Theory_Usage_Log|Active_Theories)"\s*:\s*([^}]*)', json_str, re.IGNORECASE)
                        if fallback_match:
                            active_theories = [t for t in re.findall(r'"([^"]+)"', fallback_match.group(1)) if len(t) > 3 and not t.isdigit()]
                    
                    # ==========================================
                    # 【新增】：将理论计数准确写入对应的角色/群组 JSON
                    # ==========================================
                    if active_theories:
                        try:
                            db = load_theory_db(session_id)
                            for t in active_theories: db[t] = db.get(t, 0) + 1
                            save_theory_db(db, session_id)
                            print(f"📈 [THEORY DB UPDATED]: +1 to {active_theories} (in theory_db_{get_db_filename(session_id)})")
                            turn_events.append(f"📈 数据库【{session_id}】更新: {active_theories} 计数 +1")
                        except Exception:
                            pass

                story_text = re.sub(r'</?thinking>', '', story_text, flags=re.IGNORECASE)

                if not story_text:
                    story_text = "\n\n*[System Warning: 模型没有输出小说正文，或者被前端截断了。]*\n\n"

                html_ui = ''
                if thought_text or json_str or turn_events:
                    safe_thought = pyhtml.escape(thought_text).replace('\n', '<br>')
                    safe_json = pyhtml.escape(json_str)
                    
                    events_html = "<br>".join([f"&nbsp;&nbsp;{pyhtml.escape(evt)}" for evt in turn_events])
                    
                    html_ui += f'<details>\n<summary><span style="color: #00FF00; font-family: monospace; cursor: pointer;">[+] EODHCTSiqsxajs Cognitive Matrix (Click to Expand)</span></summary>\n<blockquote style="border-left: 3px solid #00FF00; background-color: rgba(0,255,0,0.05); padding: 10px; margin-top: 5px; color: #aaa; font-size: 0.9em; line-height: 1.4;">\n'
                    
                    if events_html:
                        html_ui += f'<div style="color: #FFA500; margin-bottom: 10px; border-bottom: 1px dashed #FFA500; padding-bottom: 5px;"><strong>[📡 代理服务器系统日志]:</strong><br>{events_html}</div>\n'
                    
                    if safe_thought:
                        html_ui += f'{safe_thought}\n'
                    if safe_json:
                        html_ui += f'<hr style="border: 1px dashed #00FF00; opacity: 0.5; margin: 10px 0;">\n<pre style="background: transparent; border: none; color: #00FFFF; margin: 0; white-space: pre-wrap; font-family: monospace; font-size: 0.9em;">{safe_json}</pre>\n'
                    html_ui += '</blockquote>\n</details>\n<hr style="border: 1px dashed #555; margin: 15px 0;">\n\n'

                final_reply = html_ui + story_text
                
                return final_reply.strip(), "stop"

        return "SIMULATION ERROR: Maximum ReAct iterations reached.", "length"

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    req_data = await request.json()
    is_stream = req_data.get("stream", False)
    req_data["stream"] = False
        
    final_output, actual_finish_reason = await run_react_loop(req_data)
    
    if is_stream:
        async def generate():
            chunk_start = {
                "id": "chatcmpl-react-proxy", "object": "chat.completion.chunk", "created": 1234567890,
                "model": req_data.get("model", "react-engine"),
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": final_output}, "finish_reason": None}]
            }
            yield f"data: {json.dumps(chunk_start)}\n\n"
            
            chunk_end = {
                "id": "chatcmpl-react-proxy", "object": "chat.completion.chunk", "created": 1234567890,
                "model": req_data.get("model", "react-engine"),
                "choices": [{"index": 0, "delta": {}, "finish_reason": actual_finish_reason}]
            }
            yield f"data: {json.dumps(chunk_end)}\n\n"
            yield "data: [DONE]\n\n"
            
        return StreamingResponse(generate(), media_type="text/event-stream")
        
    else:
        return JSONResponse({
            "id": "chatcmpl-react-proxy",
            "object": "chat.completion",
            "created": 1234567890,
            "model": req_data.get("model", "react-engine"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": final_output}, "finish_reason": actual_finish_reason}]
        })

@app.get("/v1/models")
async def get_models():
    return {"object": "list", "data": [{"id": "react-engine", "object": "model", "created": 1686935002, "owned_by": "eodhctsiqsxajs"}]}

if __name__ == "__main__":
    print("🚀 EODHCTSiqsxajs ReAct Middleware starting on port 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)