#!/usr/bin/env python3
"""将 dw.db 中战斗机/无人机相关文章迁移到 aam.db。

在 theme.py 的关键词和 LLM 过滤规则变更后，执行此脚本将
现有文章从 dw.db 移至 aam.db。"""
import os, sqlite3, sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 已被从 DW 移到 AAM 的战斗机/无人机/空战关键词
FIGHTER_UAV_KEYWORDS = [
    # Air combat general
    "空战", "air combat",
    "制空权", "air superiority", "空中优势",
    "air dominance",
    "超视距空战", "BVR combat", "近距格斗",
    "dogfight", "WVR combat", "空中交战",
    "夺取制空权", "空战战术",
    "空战训练", "air combat exercise",
    "空战模拟", "air combat simulation",
    # Chinese fighters & UAVs
    "歼-20", "J-20", "歼-10", "歼-16", "歼轰-7",
    "歼-36", "J-36", "歼-50", "J-50",
    "歼-15", "歼-15T", "J-15",
    "六代机", "第六代战斗机", "sixth-generation China",
    "隐身战机", "stealth fighter China",
    "无人机", "UAV China", "攻击-11", "GJ-11",
    "翔龙", "彩虹", "翼龙", "无侦-8",
    "Chinese drone", "unmanned China military",
    "教练机", "trainer aircraft China",
    "发动机&&歼", "涡扇&&中国",
    # US fighters & UAVs
    "F-35", "F-22", "F-15", "F-16", "F/A-18",
    "NGAD", "Next Generation Air Dominance",
    "CCA", "Collaborative Combat Aircraft",
    "六代机美国", "美国六代机",
    "MQ-9", "MQ-4", "RQ-4", "Global Hawk",
    # European fighters
    "Eurofighter", "Typhoon", "Rafale", "阵风",
    "GCAP", "Global Combat Air Programme",
    "FCAS", "SCAF", "未来空战系统",
    "TEMPEST", "暴风雨", "六代机欧洲",
    # Russian fighters
    "Su-27", "Su-30", "Su-34", "Su-35", "Su-57",
    "MiG-29", "MiG-31", "MiG-35",
    "俄罗斯战机", "Russian fighter",
    # Indian fighters
    "Su-30MKI", "Rafale India", "Tejas",
    "AMCA", "印度五代机", "印度六代机",
    # Japan/Korea fighters
    "F-15J", "F-2", "日本战机", "日本六代机",
    "KF-21", "韩国战机", "韩国五代机",
]


def _matches_fighter_uav(kw: str) -> bool:
    """检查 matched_kw 字段是否匹配任何战斗机/无人机关键词"""
    if not kw:
        return False
    kw_lower = kw.lower()
    for fk in FIGHTER_UAV_KEYWORDS:
        if "&&" in fk:
            parts = [p.strip().lower() for p in fk.split("&&")]
            if all(p in kw_lower for p in parts):
                return True
        elif fk.lower() in kw_lower:
            return True
    return False


def main():
    dw_path = os.path.join(BASE_DIR, "data", "dw.db")
    aam_path = os.path.join(BASE_DIR, "data", "aam.db")

    if not os.path.exists(dw_path):
        print("dw.db 不存在")
        sys.exit(1)
    if not os.path.exists(aam_path):
        print("aam.db 不存在")
        sys.exit(1)

    dw = sqlite3.connect(dw_path)
    aam = sqlite3.connect(aam_path)

    # 确保 aam.db 有必要的列
    from schema import EXTRA_COLUMNS
    for col_name, col_type in EXTRA_COLUMNS:
        try:
            aam.execute(f"SELECT {col_name} FROM articles LIMIT 1")
        except sqlite3.OperationalError:
            aam.execute(f"ALTER TABLE articles ADD COLUMN {col_name} {col_type}")
    aam.commit()

    # 获取所有 fighter/UAV 文章
    rows = dw.execute(
        "SELECT * FROM articles WHERE matched_kw != ''"
    ).fetchall()
    cols = [d[1] for d in dw.execute("PRAGMA table_info(articles)").fetchall()]

    matched = []
    for row in rows:
        row_dict = dict(zip(cols, row))
        if _matches_fighter_uav(row_dict.get("matched_kw", "")):
            matched.append(row_dict)

    print(f"dw.db 中匹配 fighter/UAV 关键词的文章: {len(matched)}")

    # 检查 aam.db 中已存在的 ID
    existing_ids = set(r[0] for r in aam.execute("SELECT id FROM articles").fetchall())

    to_insert = [m for m in matched if m["id"] not in existing_ids]
    already = [m for m in matched if m["id"] in existing_ids]

    print(f"  需迁移: {len(to_insert)}")
    print(f"  已在 AAM: {len(already)}")

    if not to_insert:
        print("没有需要迁移的文章")
        dw.close()
        aam.close()
        return

    # 插入到 aam.db
    insert_cols = cols  # same columns
    placeholders = ", ".join("?" for _ in insert_cols)
    col_names = ", ".join(insert_cols)

    inserted = 0
    errors = 0
    for m in to_insert:
        try:
            values = [m[c] for c in insert_cols]
            aam.execute(
                f"INSERT OR IGNORE INTO articles ({col_names}) VALUES ({placeholders})",
                values,
            )
            if aam.total_changes > 0:
                inserted += 1
        except Exception as e:
            errors += 1
            print(f"  ✗ 插入失败: {m['id'][:20]}... {e}")

    aam.commit()
    print(f"  成功插入: {inserted}")

    # 从 dw.db 删除已迁移的文章
    to_delete_ids = [m["id"] for m in to_insert]
    for aid in to_delete_ids:
        dw.execute("DELETE FROM articles WHERE id = ?", (aid,))
    dw.commit()
    print(f"  从 dw.db 删除: {len(to_delete_ids)}")

    # 验证
    dw_remaining = dw.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    print(f"\n迁移后: dw.db = {dw_remaining} 篇, aam.db = {aam.execute('SELECT COUNT(*) FROM articles').fetchone()[0]} 篇")

    print("\n完成!")

    dw.close()
    aam.close()


if __name__ == "__main__":
    main()
