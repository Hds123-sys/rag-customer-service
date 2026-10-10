"""
端到端接口自检脚本

用法:
    # 1) 先启动后端: uvicorn app.main:app --port 8000
    # 2) 运行:        python verify.py
    #    可选参数:    python verify.py --base-url http://127.0.0.1:8000

脚本会依次验证: 注册/登录/鉴权 -> 文档上传(去重/校验/PDF/MD) -> 混合检索问答
-> 会话历史 -> 删除 -> 清空 -> 密码重置, 并输出 PASS/FAIL 汇总。
"""
import argparse
import random
import string
import sys
import time

import httpx

PASSED = []
FAILED = []
WARNED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print(f"  [PASS] {name} {detail}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name} {detail}")
    return bool(condition)


def warn(name, detail=""):
    WARNED.append(name)
    print(f"  [WARN] {name} {detail}")


def random_name(prefix):
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}_{suffix}"


def make_pdf_bytes() -> bytes:
    try:
        import pymupdf
    except ImportError:
        return b""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 100), "Warranty: 24 months for all products.", fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--skip-llm", action="store_true", help="跳过依赖大模型的问答检查")
    args = parser.parse_args()

    username = random_name("verify")
    email = f"{username}@example.com"
    password = "Passw0rd123"

    print(f"目标服务: {args.base_url}")
    with httpx.Client(base_url=args.base_url, timeout=180.0) as client:
        # ---------------- 健康检查 ----------------
        print("\n[1] 健康检查")
        try:
            health = client.get("/health")
            check("GET /health 返回 200", health.status_code == 200, health.text[:120])
            body = health.json()
            check("知识库组件就绪", body.get("knowledge_base", {}).get("ready") is True,
                  str(body.get("knowledge_base", {}).get("error")))
        except Exception as exc:  # noqa: BLE001
            check("GET /health 可访问", False, str(exc))
            return 1

        # ---------------- 注册 / 登录 ----------------
        print("\n[2] 用户注册与登录")
        response = client.post("/api/auth/register",
                               json={"username": username, "email": email, "password": password})
        check("注册成功", response.status_code == 200, response.text[:160])
        token = response.json().get("access_token", "") if response.status_code == 200 else ""
        check("注册返回 token", bool(token))

        duplicate = client.post("/api/auth/register",
                                json={"username": username, "email": email, "password": password})
        check("重复注册被拒绝(400)", duplicate.status_code == 400, str(duplicate.status_code))

        login = client.post("/api/auth/login", json={"username": username, "password": password})
        check("登录成功", login.status_code == 200, login.text[:160])
        token = login.json().get("access_token", token)

        bad_login = client.post("/api/auth/login", json={"username": username, "password": "wrong"})
        check("错误密码被拒绝(401)", bad_login.status_code == 401, str(bad_login.status_code))

        auth = {"Authorization": f"Bearer {token}"}
        me = client.get("/api/auth/me", headers=auth)
        check("GET /api/auth/me 返回当前用户", me.status_code == 200 and me.json().get("username") == username)

        unauthorized = client.get("/api/documents")
        check("未携带 Token 访问受保护接口(401)", unauthorized.status_code == 401, str(unauthorized.status_code))

        # ---------------- 文档上传 ----------------
        print("\n[3] 文档上传与校验")
        doc_text = (
            "退款政策说明\n"
            "1. 用户在下单后 7 天内可以申请无理由退款。\n"
            "2. 退款审核通过后, 款项将在 1-3 个工作日内原路退回。\n"
            "3. 如遇节假日, 到账时间可能顺延至 5 个工作日。\n"
            "配送说明: 默认顺丰快递, 48 小时内发货, 全国 2-4 天送达。\n"
        )
        upload = client.post("/api/documents/upload", headers=auth,
                             files={"file": ("refund_faq.txt", doc_text.encode("utf-8"), "text/plain")})
        check("上传 TXT 成功", upload.status_code == 200, upload.text[:160])
        doc_id = upload.json().get("id", "") if upload.status_code == 200 else ""
        check("返回文档ID与片段数", bool(doc_id) and upload.json().get("chunks", 0) > 0,
              f"chunks={upload.json().get('chunks') if upload.status_code == 200 else '-'}")

        again = client.post("/api/documents/upload", headers=auth,
                            files={"file": ("refund_faq.txt", doc_text.encode("utf-8"), "text/plain")})
        check("相同内容重复上传自动去重", again.status_code == 200 and again.json().get("id") == doc_id)

        pdf_bytes = make_pdf_bytes()
        if pdf_bytes:
            pdf_upload = client.post("/api/documents/upload", headers=auth,
                                     files={"file": ("manual.pdf", pdf_bytes, "application/pdf")})
            check("上传 PDF 成功", pdf_upload.status_code == 200, pdf_upload.text[:160])
            pdf_id = pdf_upload.json().get("id", "") if pdf_upload.status_code == 200 else ""
        else:
            pdf_id = ""
            warn("跳过 PDF 上传", "缺少 pymupdf")

        md_upload = client.post("/api/documents/upload", headers=auth,
                                files={"file": ("guide.md", "# 使用指南\n\n安装失败请检查磁盘空间。".encode("utf-8"), "text/markdown")})
        check("上传 MD 成功", md_upload.status_code == 200, md_upload.text[:160])
        md_id = md_upload.json().get("id", "") if md_upload.status_code == 200 else ""

        bad_upload = client.post("/api/documents/upload", headers=auth,
                                 files={"file": ("virus.exe", b"MZ", "application/octet-stream")})
        check("不支持的类型被拒绝(400)", bad_upload.status_code == 400, str(bad_upload.status_code))

        listing = client.get("/api/documents", headers=auth)
        check("文档列表可读取", listing.status_code == 200 and len(listing.json()) >= 1,
              f"count={len(listing.json()) if listing.status_code == 200 else '-'}")

        stats = client.get("/api/documents/stats", headers=auth)
        check("知识库统计正常", stats.status_code == 200 and stats.json().get("vector_points", 0) > 0,
              str(stats.json().get("vector_backend")))

        # ---------------- 问答 ----------------
        print("\n[4] 智能问答(混合检索)")
        session_id = f"verify-{int(time.time())}"
        chat = client.post("/api/chat", headers=auth,
                           json={"message": "退款多久能到账？", "session_id": session_id})
        if args.skip_llm:
            warn("跳过问答检查")
        elif chat.status_code == 200:
            payload = chat.json()
            check("问答返回答案", bool(payload.get("answer")), payload.get("answer", "")[:80])
            check("问答返回参考来源", len(payload.get("sources", [])) > 0,
                  f"sources={len(payload.get('sources', []))}")
            source = (payload.get("sources") or [{}])[0]
            check("来源包含文件名与相似度", bool(source.get("filename")) and source.get("score") is not None)
        elif chat.status_code == 503:
            warn("问答不可用(大模型未配置)", chat.text[:120])
        else:
            check("问答返回 200", False, f"{chat.status_code} {chat.text[:160]}")

        history = client.get(f"/api/chat/history/{session_id}", headers=auth)
        check("会话历史可读取", history.status_code == 200)

        cleared = client.delete(f"/api/chat/history/{session_id}", headers=auth)
        check("清空指定会话历史", cleared.status_code == 200)

        # ---------------- 密码重置 ----------------
        print("\n[5] 密码重置")
        reset = client.post("/api/auth/reset-password", json={"email": email})
        check("请求验证码成功", reset.status_code == 200, reset.text[:120])
        code = reset.json().get("dev_code") if reset.status_code == 200 else None
        if code:
            wrong = client.post("/api/auth/reset-password/confirm",
                                json={"email": email, "code": "000000", "new_password": "NewPassw0rd"})
            check("错误验证码被拒绝(400)", wrong.status_code == 400, str(wrong.status_code))

            confirm = client.post("/api/auth/reset-password/confirm",
                                  json={"email": email, "code": code, "new_password": "NewPassw0rd"})
            check("使用正确验证码重置成功", confirm.status_code == 200, confirm.text[:120])

            relogin = client.post("/api/auth/login", json={"username": username, "password": "NewPassw0rd"})
            check("使用新密码登录成功", relogin.status_code == 200, str(relogin.status_code))
        else:
            warn("开发模式未返回验证码, 跳过重置验证")

        # ---------------- 删除与清空 ----------------
        print("\n[6] 文档删除与清空")
        if md_id:
            deleted = client.delete(f"/api/documents/{md_id}", headers=auth)
            check("删除单个文档", deleted.status_code == 200, deleted.text[:120])
        if pdf_id:
            client.delete(f"/api/documents/{pdf_id}", headers=auth)

        missing = client.delete("/api/documents/not-exist-id", headers=auth)
        check("删除不存在的文档返回 404", missing.status_code == 404, str(missing.status_code))

        clear = client.post("/api/documents/clear", headers=auth)
        check("清空所有文档", clear.status_code == 200, clear.text[:120])

        after = client.get("/api/documents", headers=auth)
        check("清空后文档列表为空", after.status_code == 200 and len(after.json()) == 0,
              f"count={len(after.json()) if after.status_code == 200 else '-'}")

        after_stats = client.get("/api/documents/stats", headers=auth)
        check("清空后向量库为空", after_stats.status_code == 200 and after_stats.json().get("vector_points") == 0,
              f"points={after_stats.json().get('vector_points') if after_stats.status_code == 200 else '-'}")

    print("\n" + "=" * 56)
    print(f"通过 {len(PASSED)} 项, 失败 {len(FAILED)} 项, 警告 {len(WARNED)} 项")
    if FAILED:
        print("失败项: " + ", ".join(FAILED))
    print("=" * 56)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())