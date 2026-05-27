from app.task1.vector_store import VectorStore

vs = VectorStore(persist_dir='./data/chroma_db')

# extractor.py 中使用的 5 个多查询
queries = [
    '4gaboards 用户手册 Board 卡片 列表 视图 快捷键',
    '4gaboards 管理员手册 实例设置 管理员设置 项目设置 结构',
    '4gaboards 开发者手册 API 通知 导入导出 侧边栏',
    '4gaboards 创建 编辑 删除 管理 设置 配置',
    '4gaboards 账号 登录 注册 项目 成员 权限',
]

seen_ids = set()
all_chunks = []

for q in queries:
    chunks = vs.retrieve(query=q, n_results=60)
    new_count = 0
    for c in chunks:
        if c.id not in seen_ids:
            seen_ids.add(c.id)
            all_chunks.append(c)
            new_count += 1
    print(f'查询: \"{q}\"')
    print(f'  返回 {len(chunks)} 个, 新增 {new_count} 个 (去重后累计
{len(all_chunks)})')

print(f'\n总去重 chunks: {len(all_chunks)}')

# 看哪些页面被覆盖了
from collections import Counter
page_counts = Counter(c.source_url for c in all_chunks)
print(f'\n各页面被检索到的 chunk 数:')
for url, count in page_counts.most_common():
    print(f'  {url}: {count} chunks')