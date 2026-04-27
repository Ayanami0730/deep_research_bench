<h1 align="center">DeepResearch Bench: A Comprehensive Benchmark for Deep Research Agents</h1>

<div align="center">
<a href="https://github.com/Ayanami0730/deep_research_bench/blob/main/LICENSE"><img src="https://img.shields.io/badge/Code_License-MIT-blue" alt="license"></a>
<a href="https://deepresearch-bench.github.io/"><img src="https://img.shields.io/badge/Website-DeepResearch-green" alt="website"></a>
<a href="https://huggingface.co/datasets/muset-ai/DeepResearch-Bench-Dataset"><img alt="Dataset" src="https://img.shields.io/badge/🤗%20Dataset-orange?color=FF6F00"></a>
<a href="https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard"><img alt="Leaderboard" src="https://img.shields.io/badge/🏆%20Leaderboard-yellow?color=FFD700"></a>
<a href="https://huggingface.co/spaces/Ayanami0730/DeepResearch-Leaderboard"><img alt="Hugging Face" src="https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-blue?color=8A2BE2"></a>
<a href="https://arxiv.org/abs/2506.11763" target="_blank"><img src=https://img.shields.io/badge/arXiv-b5212f.svg?logo=arxiv></a>
<a href="https://agi-eval.cn/evaluation/detail?id=67"><img src="https://img.shields.io/badge/🤝%20AGI--Eval-purple?color=8569f6" alt="AGI-Eval"></a>
</div>

<h5 align="center"> If you like our project, please give us a star ⭐ on GitHub for the latest update.</h5>

# ✨ News
+ [27 Apr 2026] 🎉 **New Model Added**: We welcome [**LINK-Researcher**](https://nju-link.github.io/LINK-Researcher/) — a deep research agent by NJU&Alibaba, achieving an overall score of **56.04**. Check out the updated rankings on our [**Leaderboard**](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard).

+ [24 Apr 2026] 📢 **Evaluation Model Migration Notice**:

  > **⚠️ Google has announced that Gemini-2.5-Pro will be deprecated on June 17, 2026** ([details](https://ai.google.dev/gemini-api/docs/deprecations)). We are planning the migration of our evaluation model accordingly:
  >
  > - **Before May**: We will run comparison experiments to evaluate the alignment between several next-generation models and human judgments, and select the model with the highest alignment as the new official evaluator.
  > - **First week of May**: We will announce the new official evaluation model.
  > - **May**: During May, we will accept both Gemini-2.5-Pro scores and new-model scores. We will gradually re-evaluate previous submissions and migrate them to the new leaderboard. Scores from different evaluation models will be displayed and ranked on separate leaderboards.
  > - **June**: We will stop accepting Gemini-2.5-Pro evaluation results, deprecate the old leaderboard rankings, and fully switch to the new evaluation-model leaderboard.
  >
  > Before the new evaluator is officially announced, we **continue to accept Gemini-2.5-Pro-based evaluation results** as before.

+ [16 Apr 2026] 🎉 **Model Updated**: [**Cellcog Max**](https://www.cellcog.ai/) has submitted updated results, achieving an overall score of **56.67** and ranking **#2** on the leaderboard! Check out the updated rankings on our [**Leaderboard**](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard).

+ [16 Apr 2026] 🎉 **New Model Added**: We welcome [**Xiaoyi DeepResearch**](https://xiaoyi.huawei.com/chat/research) — a proprietary deep research agent, achieving an overall score of **57.00** and ranking **#1** on the leaderboard! Check out the updated rankings on our [**Leaderboard**](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard).

+ [16 Apr 2026] 🎉 **New Model Added**: We welcome [**Deep Dog 1**](https://github.com/beneadie/DeepDog_1) — an open-source deep research agent (MIT license), achieving an overall score of **53.52**. Check out the updated rankings on our [**Leaderboard**](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard).

+ [13 Apr 2026] 🎉 **New Models Added**: We welcome two new models to DeepResearch Bench:
  - 🥇 [**Grep Deep Research**](https://grep.ai) — a proprietary deep research agent, achieving **#1** with an overall score of **56.23**.
  - [**LiAuto Mind DeepResearch 1.5**](https://www.lixiang.com/tech/mindgpt) — a proprietary deep research agent by 理想汽车, achieving an overall score of **52.54**.
  
  Check out the updated rankings on our [**Leaderboard**](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard).

+ [9 Apr 2026] 🎉 **New Model Added**: We welcome [**MS-Agent Agentic Insight v2（Qwen3.5-Plus、GPT 5.2）**](https://github.com/modelscope/ms-agent) — an open-source deep research agent (Apache-2.0 license), achieving an overall score of **55.31**. Check out the updated rankings on our [**Leaderboard**](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard).

+ [2 Apr 2026] 🎉 **New Model Added**: We welcome [**Grep.ai Deep Research**](https://grep.ai) — a proprietary deep research agent, achieving an overall score of **56.09** and ranking **#2** on the leaderboard! Check out the updated rankings on our [**Leaderboard**](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard).

+ [2 Apr 2026] 🎉 **New Models Added**: We welcome two new models to DeepResearch Bench:
  - 🥉 [**1688AILab-DeepResearch**](https://air.1688.com/kapp/1688-ai-app/pages/home) — a proprietary deep research agent, achieving **#3** with an overall score of **55.39**.
  - [**TrajectoryKit (GPT-OSS, GPT5.4)**](https://github.com/KabakaWilliam/trajectorykit) — an open-source deep research agent (MIT license), achieving an overall score of **54.92**.
  
  Check out the updated rankings on our [**Leaderboard**](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard).

+ [31 Mar 2026] 📝 **Leaderboard Submission Update**: We have clarified the official leaderboard submission requirements in the README. Submissions should now include a temporary **Gemini-2.5-Pro** accessible key, the **raw generated reports**, reproducibility links (repository or product/API link), and model metadata such as **model name, link, and open-source license**. Please contact **dumingxuan@mail.ustc.edu.cn** and **imlrz@mail.ustc.edu.cn** for submission, and see [**Submit to Leaderboard**](#submit-to-leaderboard) for details.

+ [25 Mar 2026] 🎉 **New Model Added**: We welcome [**MS-Agent Agentic Insight v2（Qwen3.5-Plus、GPT 5）**](https://github.com/modelscope/ms-agent) — an open-source deep research agent (Apache-2.0 license), achieving an overall score of **54.97**. Check out the updated rankings on our [**Leaderboard**](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard).

+ [20 Mar 2026] 🎉 **New Models Added**: We welcome three new models to DeepResearch Bench:
  - 🥇 [**Cellcog Max**](https://www.cellcog.ai/) — a proprietary deep research agent, achieves **#1** with an overall score of **56.13**!
  - 🥉 [**Cellcog**](https://www.cellcog.ai/) — a proprietary deep research agent, achieves **#3** with an overall score of **55.31**.
  - [**RecallRadar Intelligence**](https://getrecallradar.com) — a proprietary deep research agent, achieving an overall score of **53.19**.
  
  Check out the updated rankings on our [**Leaderboard**](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard).


+ [6 Feb 2026] 🚀 **DeepResearch Bench II Release**: We have released **DeepResearch Bench II (DRB II)** ([homepage](https://agentresearchlab.org/benchmarks/deepresearch-bench-ii/index.html#home)｜[repo](https://github.com/imlrz/DeepResearch-Bench-II)｜[paper](https://arxiv.org/abs/2601.08536)). We welcome you to evaluate and exchange ideas. Note that DRB II, as a follow-up to DRB, has a different evaluation focus from DRB; **DRB will continue to be maintained and updated** after the release of DRB II. For more details, please refer to the [DRB II paper](https://arxiv.org/abs/2601.08536).

+ [6 Feb 2026] 📚 **New Papers from Our Lab**: We welcome you to check out the new papers from our lab ([Agent Research Lab](https://agentresearchlab.org/index.html)):
  - **Benchmarks**:
    - [DeepResearch Bench II](https://arxiv.org/abs/2601.08536): Evaluates DRA-generated reports with 9,430 fine-grained binary rubrics (information recall, analysis, presentation) derived from expert-written articles.
    - [Wiki Live Challenge](https://arxiv.org/abs/2602.01590): A live benchmark that uses Wikipedia Good Articles as expert-level references, with fine-grained criteria for writing quality and factual verifiability.
    - [WildGraphBench](https://arxiv.org/abs/2602.02053): Benchmarks GraphRAG on long, heterogeneous documents with 1,100 questions spanning single-fact QA, multi-fact QA, and section-level summarization.
  - **Agents**:
    - [A-RAG](https://arxiv.org/abs/2602.03442): An agentic RAG framework that exposes hierarchical retrieval interfaces (keyword search, semantic search, chunk read) to the model for adaptive multi-granularity retrieval.
    - [FS-Researcher](https://arxiv.org/abs/2602.01566): A file-system-based dual-agent framework (Context Builder + Report Writer) that scales deep research beyond the context window via a persistent knowledge base.
  
  **If you want to evaluate your deep research agent** please see the leaderboard submission requirements below and contact us at dumingxuan@mail.ustc.edu.cn and imlrz@mail.ustc.edu.cn.
+ [18 July 2025] 🎉 We have established a partnership with **AGI-Eval** platform. DeepResearch Bench is now available on [**AGI-Eval**](https://agi-eval.cn/evaluation/detail?id=67), providing a more convenient evaluation interface for researchers and practitioners to test their deep research agents.
+ [15 July 2025] ⚡️⚡️ **Major Update**: Added comprehensive evaluation of **Kimi-Researcher**, **Doubao-DeepResearch**, and **Claude-Researcher**. Upgraded evaluation infrastructure with **Gemini-2.5-Pro** for RACE and **Gemini-2.5-Flash** for FACT evaluation. All raw research articles and evaluation scores are now available on our [**Hugging Face Leaderboard**](https://huggingface.co/spaces/Ayanami0730/DeepResearch-Leaderboard) for comprehensive analysis and comparison.

For detailed evaluation results and comprehensive comparisons, please refer to the evaluation results table below.




## 📖 Overview

DeepResearch Bench addresses the absence of a comprehensive benchmark for systematically evaluating Deep Research Agents (DRAs). Our benchmark consists of **100 PhD-level research tasks**, each meticulously crafted by domain experts across **22 distinct fields**, including:

* 🔬 **Science & Technology**: Physics, chemistry, biology, environmental science, and engineering
* 💼 **Finance & Business**: investments, personal finance, marketing, and human resources
* 💻 **Software**: Topics related to the use of software and the internet
* 🌍 **Others**: Art & Design, Entertainment, History, Industrial, Transportation, Travel, and more


## Benchmark Construction

### Topic Distribution Analysis

To ensure DeepResearch Bench reflects real-world research demands, we analyzed **96,147 anonymized user queries** from web search-enabled LLM interactions.These queries were classified into **22 topic domains** based on the WebOrganizer taxonomy, revealing the authentic distribution of human deep research needs across different fields.

### Expert Task Collection

Guided by real-world demand distribution, we invited **PhD-level experts and senior practitioners** (5+ years experience) to design challenging research tasks within their domains. Each submission underwent rigorous manual screening for:

- **Quality**: High research standards and complexity
- **Clarity**: Clear task definitions and requirements  
- **Authenticity**: Grounded in real research scenarios
- **Challenge Level**: Testing upper limits of DRA capabilities

This process yielded **100 high-quality benchmark tasks** (50 Chinese, 50 English) that maintain the same topical balance as observed in real-world usage.


## Evaluation Framework

![Framework Overview](pics/framework.png)

DeepResearch Bench introduces two complementary evaluation methodologies designed to comprehensively assess Deep Research Agents:

### 🎯 RACE (Reference-based Adaptive Criteria-driven Evaluation)

RACE evaluates **report generation quality** through a sophisticated multi-step process:

- **Dynamic Criteria Generation**: Automatically generates task-specific evaluation criteria across four key dimensions:
  - 📚 **Comprehensiveness**: Coverage breadth and depth of the research topic
  - 🔍 **Insight/Depth**: Quality of analysis and insight generation  
  - 📋 **Instruction-Following**: Adherence to specific task requirements
  - 📖 **Readability**: Clarity, organization, and presentation quality

- **Reference-Based Scoring**: Compares target reports against high-quality reference reports to ensure discriminative evaluation
- **Weighted Assessment**: Uses dynamic weights adapted to each task's specific requirements

### 🔗 FACT (Framework for Factual Abundance and Citation Trustworthiness)

FACT evaluates **information retrieval and grounding capabilities** through:

- **Statement-URL Extraction**: Automatically extracts factual claims and their cited sources from generated reports
- **Deduplication**: Removes redundant statement-URL pairs to focus on unique factual claims
- **Support Verification**: Uses web scraping and LLM judgment to verify whether cited sources actually support the claims
- **Citation Metrics**: Calculates:
  - **Citation Accuracy**: Percentage of correctly supported citations
  - **Effective Citations**: Average number of verifiably supported citations per task


## 📊 Evaluation Results

### Main Results

**View Latest Leaderboard**: Visit our [**DeepResearch Bench Leaderboard**](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard) for real-time updated evaluation results, detailed comparative analysis, and raw data.

### Submit to Leaderboard

If you would like to obtain an **official leaderboard entry** on DeepResearch Bench, please prepare the following materials and send them by email to:

- `dumingxuan@mail.ustc.edu.cn`
- `imlrz@mail.ustc.edu.cn`

**Required submission materials:**

1. **A temporary key with access to Gemini-2.5-Pro**
   - This key is used only for verification/evaluation.
   - It should remain valid during the evaluation window.
   - Supported examples include:
     - Google AI Studio
     - Vertex AI
     - OpenRouter
     - Other official providers with Gemini-2.5-Pro access

2. **The raw generated articles**
   - Please provide your model outputs in the same format as the benchmark raw data.
   - Reference example:
     - [`data/test_data/raw_data/claude-3-7-sonnet-latest.jsonl`](https://github.com/Ayanami0730/deep_research_bench/blob/main/data/test_data/raw_data/claude-3-7-sonnet-latest.jsonl)

3. **Reproducibility link**
   - If your model/agent is **open-source**, please provide a repository link that allows others to reproduce the results.
   - If your model/agent is **closed-source**, please provide the product page and/or API link used for reproduction and verification.

4. **Model metadata**
   - **Model name**
   - **Model/project link**
   - **Open-source license** (for open-source submissions; if closed-source, please clearly indicate that it is proprietary)

**Recommended additional files:**

- `results/race/<model_name>/race_result.txt`
- `results/fact/<model_name>/fact_result.txt`

Providing these files can help us speed up verification, but the raw generated reports and the temporary evaluation key are the most important requirements.

---

## 🛠️ Installation and Usage

### Prerequisites

- Python 3.9+
- Gemini API key (for LLM evaluation)
- Jina API key (for web scraping in FACT evaluation)

### Setup

```bash
git clone https://github.com/your-username/deep_research_bench.git
cd deep_research_bench
pip install -r requirements.txt
```

### API Configuration

Set the required API keys as environment variables:

```bash
# Set Gemini API key for LLM evaluation
export GEMINI_API_KEY="your_gemini_api_key_here"

# Set Jina API key for web scraping
export JINA_API_KEY="your_jina_api_key_here"
```


## Project Structure

```
deep_research_bench/
├── data/
│   ├── criteria_data/      # Evaluation criteria data
│   ├── prompt_data/        
│   │   └── query.jsonl     # ← 100 benchmark queries for your agent
│   └── test_data/          
│       ├── cleaned_data/   # Cleaned article data
│       └── raw_data/       # ← Put your model outputs here (model_name.jsonl)
├── prompt/                 # Prompt templates
├── utils/                  # Utility functions
├── deepresearch_bench_race.py  # RACE evaluation script
├── run_benchmark.sh        # ← Add your model names here, then run
└── requirements.txt        # Dependencies
```

**Quick Start Flow:**
1. Use queries from `data/prompt_data/query.jsonl` → Run your Deep Research Agent
2. Save outputs to `data/test_data/raw_data/<model_name>.jsonl`
3. Add model name to `TARGET_MODELS` in `run_benchmark.sh`
4. Run: `bash run_benchmark.sh`

## Quick Start

### 1. Prepare Your Model Data

Run your Deep Research Agent on the benchmark queries and save outputs in the required format:

**Input**: Use queries from `data/prompt_data/query.jsonl` (100 benchmark tasks)

**Output**: Save results to `data/test_data/raw_data/<model_name>.jsonl`

**Required format** (each line should contain):
```json
{
    "id": "task_id", 
    "prompt": "original_query_text", 
    "article": "generated_research_article_with_citations"
}
```

### 2. Configure Models to Evaluate

Edit `run_benchmark.sh` and add your model name:
```bash
TARGET_MODELS=("your-model-name")
```

### 3. Run Evaluation

```bash
bash run_benchmark.sh
```

Results will be saved to:
- RACE evaluation: `results/race/<model_name>/race_result.txt`
- FACT evaluation: `results/fact/<model_name>/fact_result.txt`

### Custom LLM Integration

If you're not using the official Gemini API or want to use other LLMs for evaluation, modify the `AIClient` class in `utils/api.py` to implement your custom LLM interface.

## Acknowledgements

We would like to express our gratitude to the following contributors who helped us collect evaluation data. Since many models and agents do not provide public APIs, manual data collection was necessary, and we deeply appreciate their dedicated efforts:

**Xin Yang**, **Jie Yang**, **Yawen Li**, **Xinyu Ouyang**, **Jiaqi He**, **Gefan Zhang**, **Jinfu Liao**, **Qiuyue Chen**, **Yulin Wang**, and **Lina Wang**.

Their contributions were essential to the comprehensive evaluation presented in this benchmark.

## Citation

If you use DeepResearch Bench in your research, please cite our paper:

```bibtex
@article{du2025deepresearch,
  author    = {Mingxuan Du and Benfeng Xu and Chiwei Zhu and Xiaorui Wang and Zhendong Mao},
  title     = {DeepResearch Bench: A Comprehensive Benchmark for Deep Research Agents},
  journal   = {arXiv preprint},
  year      = {2025},
}
``` 