"""RAG 效果检查脚本 — 检查 ChromaDB chunk 质量、跨语言检索效果、模拟 RAG 全流程。

用法:
    cd backend && python3 check_rag.py

分三个部分:
    Part 1: ChromaDB 状态与 chunk 质量
    Part 2: 跨语言检索效果对比
    Part 3: 模拟特征提取 RAG 流程（检索 → 组装 context → 打印给 LLM 的完整 prompt）
"""

import chromadb
from chromadb.utils import embedding_functions
import json
import sys
import os

# ─── 配置 ───
CHROMA_DIR = "./data/chroma_db"
COLLECTION_NAME = "4gaboards_docs"
EMBEDDING_MODEL = "BAAI/bge-m3"
CRAWLED_DIR = "./data/crawled_docs"

# ─── 初始化 ───
os.makedirs(CHROMA_DIR, exist_ok=True)
client = chromadb.PersistentClient(path=CHROMA_DIR)

try:
    coll = client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL,
            local_files_only=True,
        ),
    )
    print(f"✅ 连接成功: collection='{COLLECTION_NAME}', chunks={coll.count()}")
except Exception as e:
    print(f"❌ 无法连接 collection '{COLLECTION_NAME}': {e}")
    print("   可能需要先重建索引（运行爬取+分块流程）")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════
# Part 1: ChromaDB 状态与 chunk 质量检查
# ═══════════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("Part 1: ChromaDB 状态与 chunk 质量检查")
print("="*70)

total_chunks = coll.count()
print(f"\n总 chunk 数: {total_chunks}")

# 拉取所有 chunk 进行质量分析
all_data = coll.get(limit=total_chunks, include=["documents", "metadatas"])

noise_keywords = [
    "Skip to main content", "__docusaurus_skipToContent",
    "4ga Boards Documentation", "![4ga Boards]",
    "Polski", "© 2026",
]

stats = {
    "total": total_chunks,
    "noise_heavy": 0,    # >50% 行是噪音
    "noise_medium": 0,   # 20-50% 行是噪音
    "clean": 0,          # <20% 噪音
    "thin": 0,            # <100 chars
    "source_pages": set(),
}

noise_examples = []
clean_examples = []

for i in range(total_chunks):
    doc = all_data["documents"][i]
    meta = all_data["metadatas"][i]
    source = meta.get("source_url", "?")

    stats["source_pages"].add(source)

    lines = doc.split("\n")
    noise_lines = sum(1 for l in lines if any(kw in l for kw in noise_keywords))
    noise_ratio = noise_lines / max(len(lines), 1)

    content_len = len(doc.strip())

    if content_len < 100:
        stats["thin"] += 1
    elif noise_ratio > 0.5:
        stats["noise_heavy"] += 1
        if len(noise_examples) < 3:
            noise_examples.append((all_data["ids"][i], source, noise_ratio, doc[:200]))
    elif noise_ratio > 0.2:
        stats["noise_medium"] += 1
    else:
        stats["clean"] += 1
        if len(clean_examples) < 3:
            clean_examples.append((all_data["ids"][i], source, noise_ratio, doc[:200]))

print(f"\n--- Chunk 质量分布 ---")
print(f"  干净 chunks (噪音<20%):  {stats['clean']} ({stats['clean']/total_chunks*100:.1f}%)")
print(f"  中噪音 chunks (20-50%):  {stats['noise_medium']} ({stats['noise_medium']/total_chunks*100:.1f}%)")
print(f"  重噪音 chunks (>50%):    {stats['noise_heavy']} ({stats['noise_heavy']/total_chunks*100:.1f}%)")
print(f"  过薄 chunks (<100 chars): {stats['thin']} ({stats['thin']/total_chunks*100:.1f}%)")
print(f"  覆盖页面数:              {len(stats['source_pages'])}")

# 噪音 chunk 示例
if noise_examples:
    print(f"\n--- 噪音 chunk 示例 ---")
    for id_, src, ratio, preview in noise_examples:
        print(f"  ID: {id_}")
        print(f"  Source: {src} | 噪音比: {ratio:.1%}")
        print(f"  Preview: {preview[:150]}")
        print()

# 干净 chunk 示例
if clean_examples:
    print(f"\n--- 干净 chunk 示例 ---")
    for id_, src, ratio, preview in clean_examples:
        print(f"  ID: {id_}")
        print(f"  Source: {src} | 噪音比: {ratio:.1%}")
        print(f"  Preview: {preview[:150]}")
        print()

# 每个页面的 chunk 数量分布
from collections import Counter
page_chunk_counts = Counter(meta.get("source_url", "?") for meta in all_data["metadatas"])
print(f"\n--- 各页面 chunk 数量 ---")
for page, count in page_chunk_counts.most_common():
    print(f"  {page}: {count} chunks")


# ═══════════════════════════════════════════════════════════════════
# Part 2: 跨语言检索效果对比
# ═══════════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("Part 2: 跨语言检索效果对比 (中文 vs 英文查询)")
print("="*70)

test_pairs = [
    ("How to create a board",          "如何创建一个Board"),
    ("Card creation and editing",      "Card的创建和编辑操作"),
    ("User permissions and roles",     "用户权限管理"),
    ("Notifications and alerts",       "通知和提醒功能"),
    ("Import and export data",         "导入导出数据"),
    ("Board filtering options",        "Board过滤选项"),
    ("Sidebar navigation",             "侧边栏导航"),
    ("Project settings management",    "项目设置管理"),
    ("List view operations",           "列表视图操作"),
    ("Account registration and login", "账号注册和登录"),
]

print(f"\n{'中文查询':<30} {'Top-1 source':<45} {'dist':>8} {'EN match':>8}")
print("-" * 95)

for en_q, cn_q in test_pairs:
    cn_result = coll.query(query_texts=[cn_q], n_results=3, include=["metadatas", "distances"])
    cn_top1_source = cn_result["metadatas"][0][0].get("source_url", "?")
    cn_dist = cn_result["distances"][0][0]

    en_result = coll.query(query_texts=[en_q], n_results=3, include=["metadatas", "distances"])
    en_top1_source = en_result["metadatas"][0][0].get("source_url", "?")

    match = "✅" if cn_top1_source == en_top1_source else "❌"

    print(f"{cn_q:<30} {cn_top1_source:<45} {cn_dist:>8.4f} {match:>8}")

# 详细对比: 展示每个查询的 Top-3
print(f"\n--- 详细 Top-3 对比 ---")
for en_q, cn_q in test_pairs[:5]:  # 只展示前5个
    en_result = coll.query(query_texts=[en_q], n_results=3, include=["metadatas", "distances"])
    cn_result = coll.query(query_texts=[cn_q], n_results=3, include=["metadatas", "distances"])

    print(f"\n  EN: '{en_q}'")
    for i in range(3):
        src = en_result["metadatas"][0][i].get("source_url", "?")
        dist = en_result["distances"][0][i]
        print(f"    #{i+1} dist={dist:.4f} {src}")

    print(f"  CN: '{cn_q}'")
    for i in range(3):
        src = cn_result["metadatas"][0][i].get("source_url", "?")
        dist = cn_result["distances"][0][i]
        print(f"    #{i+1} dist={dist:.4f} {src}")


# ═══════════════════════════════════════════════════════════════════
# Part 3: 模拟特征提取 RAG 全流程
# ═══════════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("Part 3: 模拟特征提取 RAG 流程 (检索 → 组装 context)")
print("="*70)

# 使用 extractor.py 中的 5 个多查询
retrieval_queries = [
    "4gaboards 用户手册 Board 卡片 列表 视图 快捷键",
    "4gaboards 管理员手册 实例设置 管理员设置 项目设置 结构",
    "4gaboards 开发者手册 API 通知 导入导出 侧边栏",
    "4gaboards 创建 编辑 删除 管理 设置 配置",
    "4gaboards 账号 登录 注册 项目 成员 权限",
]

seen_ids = set()
all_chunks_data = []
distance_stats = []

for q in retrieval_queries:
    result = coll.query(query_texts=[q], n_results=60, include=["documents", "metadatas", "distances"])
    for i in range(len(result["ids"][0])):
        id_ = result["ids"][0][i]
        dist = result["distances"][0][i]
        doc = result["documents"][0][i]
        meta = result["metadatas"][0][i]

        if id_ not in seen_ids:
            seen_ids.add(id_)
            distance_stats.append(dist)

            # 检查是否是噪音 chunk
            lines = doc.split("\n")
            noise_lines = sum(1 for l in lines if any(kw in l for kw in noise_keywords))
            noise_ratio = noise_lines / max(len(lines), 1)
            is_noise = noise_ratio > 0.4

            all_chunks_data.append({
                "id": id_,
                "source": meta.get("source_url", "?"),
                "title": meta.get("title", "?"),
                "dist": dist,
                "content_len": len(doc),
                "noise_ratio": noise_ratio,
                "is_noise": is_noise,
                "content_preview": doc[:120].replace("\n", " "),
            })

print(f"\n--- 多查询检索统计 ---")
print(f"  5个查询 x 60结果 -> 去重后: {len(all_chunks_data)} 个唯一 chunks")

# 距离分布
sorted_dists = sorted(distance_stats)
print(f"  距离范围: {sorted_dists[0]:.4f} ~ {sorted_dists[-1]:.4f}")
print(f"  距离中位数: {sorted_dists[len(sorted_dists)//2]:.4f}")

# 按质量分层
noise_count = sum(1 for c in all_chunks_data if c["is_noise"])
clean_count = len(all_chunks_data) - noise_count
high_rel = sum(1 for c in all_chunks_data if c["dist"] < 0.3)
med_rel = sum(1 for c in all_chunks_data if 0.3 <= c["dist"] < 0.5)
low_rel = sum(1 for c in all_chunks_data if c["dist"] >= 0.5)

print(f"\n--- 检索质量分层 ---")
print(f"  高相关 (dist<0.3):   {high_rel} ({high_rel/len(all_chunks_data)*100:.1f}%)")
print(f"  中相关 (0.3-0.5):    {med_rel} ({med_rel/len(all_chunks_data)*100:.1f}%)")
print(f"  低相关 (dist>=0.5):  {low_rel} ({low_rel/len(all_chunks_data)*100:.1f}%)")
print(f"  噪音 chunks:         {noise_count} ({noise_count/len(all_chunks_data)*100:.1f}%)")

# 如果去掉噪音，LLM 收到的总 context 长度
total_chars_with_noise = sum(c["content_len"] for c in all_chunks_data)
total_chars_no_noise = sum(c["content_len"] for c in all_chunks_data if not c["is_noise"])
print(f"\n--- LLM context 长度 ---")
print(f"  含噪音: {total_chars_with_noise} chars (~{total_chars_with_noise/4:.0f} tokens)")
print(f"  去噪音: {total_chars_no_noise} chars (~{total_chars_no_noise/4:.0f} tokens)")
print(f"  噪音占比: {(total_chars_with_noise-total_chars_no_noise)/total_chars_with_noise*100:.1f}%")

# 展示给 LLM 的 context 前 1000 chars（模拟实际格式）
print(f"\n--- 模拟 LLM prompt (前1000 chars) ---")
# 模拟 extractor.py 的 _format_chunks_for_prompt
sample_chunks = [c for c in all_chunks_data if not c["is_noise"]][:3]
for c in sample_chunks:
    # 拿完整 content
    full_doc_result = coll.get(ids=[c["id"]], include=["documents"])
    content = full_doc_result["documents"][0]
    formatted = f"[Chunk ID: {c['id']}]\nSource: {c['source']}\nTitle: {c['title']}\n\n{content}"
    print(formatted[:500])
    print("---")

# 检查爬取数据与 sitemap 的一致性
print(f"\n--- 爬取数据 vs Sitemap ---")
manifest_path = os.path.join(CRAWLED_DIR, "manifest.json")
if os.path.exists(manifest_path):
    pages = json.load(open(manifest_path))
    crawled_urls = set(p["url"] for p in pages)
    print(f"  已爬取页面: {len(crawled_urls)}")
    # 列出 sitemap 中应有但未爬取的功能文档 URL
    # 这里简单检查: 爬取的 URL 是否都是 /docs/ 下的
    non_docs = [u for u in crawled_urls if "/docs/" not in u and u != "https://docs.4gaboards.com/"]
    if non_docs:
        print(f"  非 docs 页面: {non_docs}")
    else:
        print(f"  ✅ 所有爬取页面都是功能文档或首页")
else:
    print(f"  ⚠️ manifest.json 不存在: {manifest_path}")


# ═══════════════════════════════════════════════════════════════════
# 最终建议
# ═══════════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("检查总结与建议")
print("="*70)

issues = []

if stats["noise_heavy"] > total_chunks * 0.1:
    issues.append(f"⚠️ 重噪音 chunks 占 {stats['noise_heavy']/total_chunks*100:.1f}%，需要在分块前清洗正文")

if stats["thin"] > 5:
    issues.append(f"⚠️ 过薄 chunks 有 {stats['thin']} 个，薄页面应排除或合并")

if total_chars_with_noise - total_chars_no_noise > total_chars_with_noise * 0.15:
    issues.append(f"⚠️ 噪音占 LLM context 的 {(total_chars_with_noise-total_chars_no_noise)/total_chars_with_noise*100:.1f}%，浪费 token")

cn_en_mismatch = 0
for en_q, cn_q in test_pairs:
    cn_r = coll.query(query_texts=[cn_q], n_results=1, include=["metadatas"])
    en_r = coll.query(query_texts=[en_q], n_results=1, include=["metadatas"])
    if cn_r["metadatas"][0][0].get("source_url") != en_r["metadatas"][0][0].get("source_url"):
        cn_en_mismatch += 1

if cn_en_mismatch > len(test_pairs) * 0.5:
    issues.append(f"⚠️ 跨语言检索命中率低: {cn_en_mismatch}/{len(test_pairs)} 组中英 Top-1 不匹配")
elif cn_en_mismatch > 0:
    issues.append(f"💡 跨语言检索部分命中: {len(test_pairs)-cn_en_mismatch}/{len(test_pairs)} 组匹配，可接受但有提升空间")
else:
    print(f"  ✅ 跨语言检索完全命中: 所有 {len(test_pairs)} 组中英 Top-1 一致")

if noise_count > len(all_chunks_data) * 0.2:
    issues.append(f"⚠️ 检索结果中噪音 chunks 占 {noise_count/len(all_chunks_data)*100:.1f}%，影响检索精度")

for issue in issues:
    print(f"  {issue}")

if not issues:
    print(f"  ✅ RAG 系统当前状态良好，无明显问题")