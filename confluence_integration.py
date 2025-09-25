# confluence_integration.py
"""
Confluence 연동 (단일 표에 '신규 증가분'만 행 추가)
- .env 로드
- 오늘자 페이지 자동 생성
- 표는 단 한 번만 만들고(id="err-table"), 이후에는 tbody(id="err-tbody")에
  '이전 호출 이후 새로 증가한 오류 수(Delta)'만 한 줄씩 추가
- 열: # | 발생 시간 | Cluster | Pattern | New(+) | Severity | Recommendation
- 상태 보존: 이전 집계값(last_count)을 페이지 본문 HTML 주석으로 저장/복구
- 실행:
    1) python -u confluence_integration.py                 # self-test (연결/페이지/표 생성/상태주석 보장)
    2) python -u confluence_integration.py --json agg.json # 집계 JSON으로 증가분만 추가
       agg.json 예시:
       {
         "total_logs": 500,
         "error_logs": 56,
         "clusters": [
           {"cluster_id": "7", "template": "NullPointer ...", "count": 25},
           {"cluster_id": "2", "template": "Database connection ...", "count": 14}
         ]
       }
"""

import os
import sys
import json
import re
from datetime import datetime
from typing import Optional, List, Tuple, Dict

# --- .env 로드 ---
print("[boot] loading .env...", flush=True)
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[ok] dotenv loaded", flush=True)
except Exception as e:
    print(f"[warn] dotenv load failed: {e}", flush=True)

# --- Confluence 라이브러리 ---
try:
    from atlassian import Confluence
    CONFLUENCE_OK = True
    print("[ok] atlassian-python-api import ok", flush=True)
except Exception as e:
    Confluence = None
    CONFLUENCE_OK = False
    print(f"[fail] import atlassian failed: {e}\n      → pip install atlassian-python-api", flush=True)


def _escape_html(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_STATE_COMMENT_KEY = "ERR_STATE"  # HTML 주석 키


class ConfluencePublisher:
    """
    외부 집계값(top_items, total_logs, error_logs)을 받아 Confluence에 날짜별로
    '단일 표'에 **신규 증가분만** 행으로 누적.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        api_token: Optional[str] = None,
        space_key: Optional[str] = None,
    ):
        self.enabled = False
        if not CONFLUENCE_OK:
            print("[stop] Confluence lib not available", flush=True)
            return

        # 환경변수
        self.url = (url or os.getenv("CONFLUENCE_URL", "")).strip()
        self.username = (username or os.getenv("CONFLUENCE_USERNAME", "")).strip()
        # ⚠️ 토큰에 '=' 포함되면 .env에서 반드시 따옴표로 감싸세요.
        self.api_token = (api_token or os.getenv("CONFLUENCE_API_TOKEN", "")).strip()
        self.space_key = (space_key or os.getenv("CONFLUENCE_SPACE_KEY", "")).strip()
        self.parent_id = (os.getenv("CONFLUENCE_PARENT_PAGE_ID") or "").strip() or None
        base_title = os.getenv("CONFLUENCE_PAGE_TITLE", "Error Report Summary").strip()

        self.date_str = datetime.now().strftime("%Y-%m-%d")
        self.page_title = f"{base_title} - {self.date_str}"

        print("[env] CONFLUENCE_URL       =", self.url or "(empty)", flush=True)
        print("[env] CONFLUENCE_USERNAME  =", self.username or "(empty)", flush=True)
        print("[env] CONFLUENCE_API_TOKEN =", ("(set)" if self.api_token else "(empty)"), flush=True)
        print("[env] CONFLUENCE_SPACE_KEY =", self.space_key or "(empty)", flush=True)
        print("[env] CONFLUENCE_PARENT_ID =", self.parent_id or "(empty)", flush=True)
        print("[env] PAGE_TITLE(base)     =", base_title, flush=True)

        if not all([self.url, self.username, self.api_token, self.space_key]):
            print("[fail] missing env: CONFLUENCE_URL/USERNAME/API_TOKEN/SPACE_KEY", flush=True)
            return

        try:
            self.client = Confluence(
                url=self.url,
                username=self.username,
                password=self.api_token,
                cloud=True,
            )
            self.enabled = True
            print("[ok] Confluence client ready", flush=True)
        except Exception as e:
            print(f"[fail] Confluence client init: {e}", flush=True)
            self.enabled = False

    # -------- Public API --------
    def test_connection(self) -> bool:
        if not self.enabled:
            print("[fail] Confluence disabled", flush=True)
            return False
        try:
            info = self.client.get_space(self.space_key)
            name = info.get("name", self.space_key) if isinstance(info, dict) else self.space_key
            print(f"[ok] space connected: {name}", flush=True)
            # 페이지 준비(없으면 생성) + 표 스켈레톤/상태 주석 보장
            page = self._get_or_create_daily_page()
            if not page:
                print("[fail] cannot prepare daily page", flush=True)
                return False
            pid = page["id"]
            cur = self.client.get_page_by_id(pid, expand="body.storage,version")
            body = cur["body"]["storage"]["value"]

            modified = False
            if 'id="err-table"' not in body:
                body = self._build_table_skeleton(total_logs=0, error_logs=0) + body
                modified = True
            if self._extract_state(body) is None:
                # 초기 상태 주석 삽입
                state = {"last_count": {}, "row_count": 0}
                body = self._upsert_state(body, state)
                modified = True

            if modified:
                self.client.update_page(
                    page_id=pid,
                    title=self.page_title,
                    body=body,
                    type="page",
                    representation="storage",
                    minor_edit=True,
                    version_comment="init table & state",
                )
                print("[ok] table skeleton & state initialized", flush=True)
            return True
        except Exception as e:
            print(f"[fail] space get: {e}", flush=True)
            return False

    def publish_summary(
        self,
        top_items: List[Tuple[str, str, int]],
        total_logs: int,
        error_logs: int,
    ) -> bool:
        """
        외부 집계값을 받아 '신규 증가분(delta)'만 행으로 누적.
        top_items 요소: (cluster_id, template, count) — count는 누적값
        """
        self._print_console(top_items, total_logs, error_logs)
        if not self.enabled:
            return True  # 콘솔만 성공 처리

        try:
            page = self._get_or_create_daily_page()
            if not page:
                print("[fail] cannot prepare daily page", flush=True)
                return False

            pid = page["id"]
            cur = self.client.get_page_by_id(pid, expand="body.storage,version")
            body = cur["body"]["storage"]["value"]
            ver = cur["version"]["number"]

            # 1) 표/상태 보장
            if 'id="err-table"' not in body:
                body = self._build_table_skeleton(total_logs, error_logs) + body
            state = self._extract_state(body)
            if state is None:
                state = {"last_count": {}, "row_count": 0}
                body = self._upsert_state(body, state)

            last_count: Dict[str, int] = dict(state.get("last_count", {}))
            row_count: int = int(state.get("row_count", 0))

            # 2) 증가분 계산
            deltas: List[Tuple[str, str, int]] = []  # (cid, tpl, delta)
            for cid, tpl, cnt in top_items:
                prev = int(last_count.get(str(cid), 0))
                delta = int(cnt) - prev
                if delta > 0:
                    deltas.append((str(cid), tpl, delta))
                    last_count[str(cid)] = int(cnt)  # 상태 갱신

            if not deltas:
                print("[info] no new errors to append (delta == 0)", flush=True)
                return True

            # 3) 행 생성 (#는 누적 행 번호)
            rows_html, added_rows = self._build_rows_with_index(deltas, start_index=row_count + 1)

            # 4) tbody에 append
            body = self._append_rows_into_table(body, rows_html)

            # 5) 상태 주석 갱신
            state["last_count"] = last_count
            state["row_count"] = row_count + added_rows
            body = self._upsert_state(body, state)

            # 6) 페이지 업데이트
            self.client.update_page(
                page_id=pid,
                title=self.page_title,
                body=body,
                type="page",
                representation="storage",
                minor_edit=True,
                version_comment=f"append delta rows {datetime.now().strftime('%H:%M:%S')}",
            )
            print(f"[ok] page updated (delta rows appended): v{ver} → v{ver+1}", flush=True)
            return True
        except Exception as e:
            print(f"[fail] publish_summary (delta append): {e}", flush=True)
            import traceback
            traceback.print_exc()
            return False

    # -------- Internals --------
    def _get_or_create_daily_page(self):
        try:
            p = self.client.get_page_by_title(self.space_key, self.page_title)
            if p:
                print(f"[ok] daily page exists: {self.page_title}", flush=True)
                return p
        except Exception:
            pass

        try:
            initial = f"""
            <h1>📊 {self.page_title}</h1>
            <div style="background:#e3f2fd;padding:10px;border-left:4px solid #2196f3;margin:10px 0;">
              <p><strong>생성:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
              <p>{self.date_str} 일자의 로그 모니터링 결과가 누적됩니다.</p>
            </div>
            <p><em>첫 업데이트 대기 중...</em></p>
            """
            res = self.client.create_page(
                space=self.space_key,
                title=self.page_title,
                body=initial,
                parent_id=self.parent_id,
            )
            print("[ok] daily page created", flush=True)
            return self.client.get_page_by_id(res["id"])
        except Exception as e:
            print(f"[fail] create daily page: {e}", flush=True)
            return None

    def _build_table_skeleton(self, total_logs: int, error_logs: int) -> str:
        """페이지에 표가 없을 때 한 번만 만들어두는 스켈레톤 (thead + tbody)"""
        rate = (error_logs / total_logs * 100) if total_logs else 0.0
        color = "green" if rate <= 20 else "orange" if rate <= 50 else "red"
        now = datetime.now().strftime("%H:%M:%S")

        header_box = f"""
        <div style="background:#f5f5f5;padding:10px;border-radius:6px;margin:8px 0;">
          <p><strong>누적:</strong> 총 {total_logs:,} / 에러 {error_logs:,}
             <span style="color:{color}"> (에러율 {rate:.1f}%)</span>
             <em style="margin-left:8px;color:#777;">초기화: {now}</em>
          </p>
        </div>
        """

        table = f"""
        <h2>🔥 에러 패턴 누적 테이블 (증가분만 표시)</h2>
        {header_box}
        <table id="err-table" style="width:100%;border-collapse:collapse;margin-top:6px;">
          <thead>
            <tr style="background:#eee;">
              <th style="border:1px solid #ddd;padding:6px;">#</th>
              <th style="border:1px solid #ddd;padding:6px;">발생 시간</th>
              <th style="border:1px solid #ddd;padding:6px;">Cluster</th>
              <th style="border:1px solid #ddd;padding:6px;">Pattern</th>
              <th style="border:1px solid #ddd;padding:6px;">New(+)</th>
              <th style="border:1px solid #ddd;padding:6px;">Severity</th>
              <th style="border:1px solid #ddd;padding:6px;">Recommendation</th>
            </tr>
          </thead>
          <tbody id="err-tbody">
          </tbody>
        </table>
        <!--{_STATE_COMMENT_KEY}:{{}}-->
        <hr/>
        """
        return table

    def _build_rows_with_index(
        self,
        deltas: List[Tuple[str, str, int]],
        start_index: int = 1,
    ) -> Tuple[str, int]:
        """증가분(deltas)에 대한 행 HTML 생성 (발생 시간 포함, #는 누적 행 번호)"""
        def sev(delta: int):
            # 증가분 기준으로 간단히 severity. 필요 시 누적 count로 바꿔도 됨.
            if delta >= 50:
                return {"icon": "🔴", "txt": "매우심각", "fg": "#d32f2f"}
            if delta >= 20:
                return {"icon": "🟠", "txt": "심각", "fg": "#ef6c00"}
            if delta >= 10:
                return {"icon": "🟡", "txt": "주의", "fg": "#f9a825"}
            return {"icon": "🟢", "txt": "경미", "fg": "#2e7d32"}

        def rec(tpl: str):
            t = (tpl or "").lower()
            if "nullpointer" in t:
                return "널체크/Optional, 널 케이스 테스트"
            if "database" in t or "connection" in t:
                return "풀 설정/누수/DB 상태 점검"
            if "outofmemory" in t:
                return "힙/프로파일링/GC 로그"
            if "filenotfound" in t:
                return "경로/권한/설정파일 확인"
            if "authentication" in t:
                return "인증 로직/토큰 만료 점검"
            if "sql" in t and "duplicate" in t:
                return "제약조건/중복 처리/트랜잭션"
            return "상세 로그/시스템 상태 추가 분석"

        now = datetime.now().strftime("%H:%M:%S")
        rows = []
        idx = start_index
        for (cid, tpl, delta) in deltas:
            s = sev(delta)
            rows.append(
                f"""
              <tr>
                <td style="border:1px solid #ddd;padding:6px;text-align:center;">{idx}</td>
                <td style="border:1px solid #ddd;padding:6px;white-space:nowrap;">{now}</td>
                <td style="border:1px solid #ddd;padding:6px;"><code>{_escape_html(str(cid))}</code></td>
                <td style="border:1px solid #ddd;padding:6px;"><code style="word-break:break-all;">{_escape_html(tpl)}</code></td>
                <td style="border:1px solid #ddd;padding:6px;text-align:center;color:{s['fg']};"><strong>{delta}</strong></td>
                <td style="border:1px solid #ddd;padding:6px;text-align:center;">{s['icon']} {s['txt']}</td>
                <td style="border:1px solid #ddd;padding:6px;font-size:0.9em;">{_escape_html(rec(tpl))}</td>
              </tr>
            """
            )
            idx += 1
        return "".join(rows), len(deltas)

    def _append_rows_into_table(self, body_html: str, rows_html: str) -> str:
        """
        body_html 내 err-table의 <tbody id="err-tbody">에 rows_html을 append.
        표가 없으면 _build_table_skeleton로 만들어놓고 오니 보통 여기선 항상 존재.
        """
        pattern = re.compile(r'(<tbody[^>]*id="err-tbody"[^>]*>)(.*?)(</tbody>)', re.DOTALL | re.IGNORECASE)
        if pattern.search(body_html):
            return pattern.sub(rf"\1\2{rows_html}\3", body_html, count=1)
        else:
            # 혹시 모를 예외: tbody를 못 찾은 경우, 테이블 전체를 다시 만들어 prepend
            print("[warn] err-tbody not found; creating table skeleton at top", flush=True)
            skeleton = self._build_table_skeleton(0, 0)
            return skeleton.replace("</tbody>", rows_html + "</tbody>") + body_html

    # ---- 상태 주석 저장/복구 ----
    def _extract_state(self, body_html: str) -> Optional[dict]:
        """
        본문에서 <!--ERR_STATE:{...}--> 형태의 JSON 상태를 찾아 dict로 반환.
        없으면 None.
        """
        # 주석 사이 공백/줄바꿈 허용
        pattern = re.compile(rf"<!--\s*{_STATE_COMMENT_KEY}\s*:\s*(\{{.*?\}})\s*-->", re.DOTALL)
        m = pattern.search(body_html)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except Exception:
            return None

    def _upsert_state(self, body_html: str, state: dict) -> str:
        """
        상태 주석을 새로 넣거나 교체.
        """
        serialized = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        new_comment = f"<!--{_STATE_COMMENT_KEY}:{serialized}-->"
        pattern = re.compile(rf"<!--\s*{_STATE_COMMENT_KEY}\s*:\s*\{{.*?\}}\s*-->", re.DOTALL)

        if pattern.search(body_html):
            return pattern.sub(new_comment, body_html, count=1)
        else:
            # 표 바로 아래에 주석이 들어가도록 시도: err-table 다음 위치 탐색
            after_table = re.compile(r'(</table>)', re.IGNORECASE)
            if after_table.search(body_html):
                return after_table.sub(rf"\1\n{new_comment}", body_html, count=1)
            # 못 찾으면 가장 위에 삽입
            return new_comment + "\n" + body_html

    def _print_console(self, top_items, total_logs, error_logs):
        rate = (error_logs / total_logs * 100) if total_logs else 0.0
        print("\n" + "=" * 70, flush=True)
        print(f"[confluence] {self.date_str} | {self.page_title}", flush=True)
        print(f"누적: 총 {total_logs:,} / 에러 {error_logs:,} (에러율 {rate:.1f}%)", flush=True)
        for i, (cid, tpl, cnt) in enumerate(top_items or [], 1):
            print(f"  {i:02d}. [cnt={cnt:>4}] CID:{cid} :: {tpl[:80]}", flush=True)
        print("=" * 70, flush=True)


# ----------------- CLI/Entry -----------------
def _load_aggregated_from_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    total = int(d.get("total_logs", 0))
    err = int(d.get("error_logs", 0))
    clusters = d.get("clusters", [])
    top_items = [(str(c.get("cluster_id")), str(c.get("template")), int(c.get("count", 0))) for c in clusters]
    return top_items, total, err


def main():
    # 옵션 파싱 (초간단)
    args = sys.argv[1:]
    json_path = None
    if len(args) >= 2 and args[0] == "--json":
        json_path = args[1]

    pub = ConfluencePublisher()
    if not json_path:
        print("[mode] self-test (연결/페이지/표/상태 주석 생성 확인)", flush=True)
        if not pub.test_connection():
            sys.exit(4)
        print("[done] self-test complete. Confluence에서 오늘 페이지/표/상태 주석 존재 확인.", flush=True)
        return

    # 실제 집계 JSON으로 증가분만 추가
    try:
        top_items, total_logs, error_logs = _load_aggregated_from_json(json_path)
        print(
            f"[load] {json_path} loaded (clusters={len(top_items)}, total={total_logs}, error={error_logs})",
            flush=True,
        )
    except Exception as e:
        print(f"[fail] load json: {e}", flush=True)
        sys.exit(2)

    ok = pub.publish_summary(top_items=top_items, total_logs=total_logs, error_logs=error_logs)
    if not ok:
        sys.exit(5)
    print("[done] appended delta rows from json aggregates.", flush=True)


if __name__ == "__main__":
    main()
