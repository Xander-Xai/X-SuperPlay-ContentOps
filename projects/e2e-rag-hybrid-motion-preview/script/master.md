# RAG 混合检索：两路召回如何合并

| 镜头 | 旁白 | 字幕 | 事实来源 | 动效 |
|---|---|---|---|---|
| rag-hybrid-01 | 混合检索并行找词项和语义候选。 | 词项与语义，两路召回 | [Elastic hybrid search](https://www.elastic.co/docs/solutions/search/hybrid-search) | `y3_whiteboard`: 关键词文档与向量候选网络逐笔出现 |
| rag-hybrid-02 | RRF 按各结果列表名次累加倒数分。 | RRF 按名次累加倒数分 | [Elastic RRF formula](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion) | `t1_3b1b`: 公式逐步书写、要点变换 |
| rag-hybrid-03 | 融合排名，避免直接比较不同原始分数。 | 融合排名，避开原始分值差异 | [Elastic RRF](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion) | `y3_whiteboard`: 合并候选网络及重点圈注 |

动画为 Huashu Art Motion 代码渲染的解释性视觉，不是检索实测结果；没有展示真实查询结果、召回指标或系统运行截图。
