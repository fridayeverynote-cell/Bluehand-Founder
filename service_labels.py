# File: service_labels.py
# 목적:
#  - bluehands 테이블에서 지점 id로 1행을 조회한다.
#  - is_* 플래그(0/1, True/False, "1"/"0", "Y"/"N" 등)를 판정해
#    값이 1인 항목만 한글 라벨 리스트/문자열로 변환한다.
#
# 환경변수(없으면 기본값):
#  - DB_HOST (default: localhost)
#  - DB_PORT (default: 3306)
#  - DB_USER (default: root)
#  - DB_PASSWORD (default: "")
#  - DB_NAME (default: bluehands_db)

from typing import Any, Dict, List, Tuple
import os
import mysql.connector


# 플래그 컬럼명 -> 사용자 표시 라벨(한글)
# - dict 선언 순서가 곧 표시 순서다(Python 3.7+).
FLAG_LABELS: Dict[str, str] = {
    # 1) 친환경차 관련
    "is_ev": "전기차 수리",
    "is_ev_tech": "전동차 기술력 우수",
    "is_hydrogen": "수소전기차 수리",

    # 2) 차체/도장 및 특수 수리
    "is_frame": "차체/도장 수리 인증",
    "is_al_frame": "알루미늄 프레임 수리",
    "is_n_line": "고성능 N 모델 수리",

    # 3) 상용차(특화/버스) 관련
    "is_commercial_mid": "중형 상용 수리",
    "is_commercial_big": "대형 상용 수리",
    "is_commercial_ev": "상용 전동차 수리",

    # 4) CS 우수
    "is_cs_excellent": "CS 우수",

    # 스키마에 is_excellent도 있지만 의미가 애매하면 표시하지 않는 편이 안전하다.
    # 필요하면 아래 주석 해제하고 라벨 확정해서 쓰면 된다.
    # "is_excellent": "우수 업체",
}


def _is_truthy_flag(value: Any) -> bool:
    """
    목적:
      - DB/CSV 값 타입이 섞여도 "참(1)"인지 판정한다.
    허용 예:
      - 1 / 0
      - True / False
      - "1" / "0"
      - "Y" / "N"
      - "true" / "false"
    """
    if value is None:
        return False

    # bool이 int의 서브클래스이므로 먼저 처리
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value == 1

    if isinstance(value, str):
        s = value.strip().lower()
        return s in ("1", "y", "yes", "true", "t")

    return False


def labels_from_row(row: Dict[str, Any]) -> List[str]:
    """
    입력:
      - row: 컬럼명 키로 접근 가능한 dict (예: {"is_ev": 1, ...})
    출력:
      - 값이 1인 플래그에 해당하는 한글 라벨 리스트
    """
    labels: List[str] = []
    for flag_key, label in FLAG_LABELS.items():
        if _is_truthy_flag(row.get(flag_key)):
            labels.append(label)
    return labels


def format_labels(labels: List[str], sep: str = " · ") -> str:
    """
    목적:
      - 라벨 리스트를 출력용 문자열로 합친다.
    """
    if not labels:
        return ""
    return sep.join(labels)


def _connect_db():
    """
    목적:
      - 환경변수로 DB 접속 정보를 읽어 MySQL 연결을 만든다.
    """
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "3306"))
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    database = os.getenv("DB_NAME", "bluehands_db")

    return mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )


def fetch_branch_row_by_id(branch_id: int) -> Dict[str, Any]:
    """
    목적:
      - bluehands 테이블에서 id로 1행을 dict 형태로 가져온다.
    반환:
      - row dict (없으면 빈 dict)
    """
    flag_cols = list(FLAG_LABELS.keys())
    cols = ["id", "name"] + flag_cols
    col_sql = ", ".join(cols)

    conn = _connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(f"SELECT {col_sql} FROM bluehands WHERE id = %s", (branch_id,))
            row = cur.fetchone()
            return row if row else {}
        finally:
            cur.close()
    finally:
        conn.close()


def get_service_labels_by_id(branch_id: int) -> List[str]:
    """
    목적:
      - 지점 id -> 값이 1인 서비스 라벨 리스트 반환
    예:
      - [ "전기차 수리", "차체/도장 수리 인증" ]
    """
    row = fetch_branch_row_by_id(branch_id)
    if not row:
        return []
    return labels_from_row(row)


def get_service_text_by_id(branch_id: int, sep: str = " · ") -> str:
    """
    목적:
      - 지점 id -> 값이 1인 서비스 라벨을 한 줄 문자열로 반환
    예:
      - "전기차 수리 · 차체/도장 수리 인증"
    """
    labels = get_service_labels_by_id(branch_id)
    return format_labels(labels, sep=sep)


def get_branch_name_and_services_by_id(branch_id: int, sep: str = " · ") -> Tuple[str, List[str], str]:
    """
    목적:
      - 지점 id -> (지점명, 라벨리스트, 합친문자열) 반환
    """
    row = fetch_branch_row_by_id(branch_id)
    if not row:
        return "", [], ""

    name = str(row.get("name", ""))
    labels = labels_from_row(row)
    text = format_labels(labels, sep=sep)
    return name, labels, text
