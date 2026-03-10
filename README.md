<div align="center">

<img src="https://capsule-render.vercel.app/api?type=venom&height=220&color=0:0c1228,50:0a2a24,100:070b18&text=BharatAlpha&fontSize=48&fontColor=f0f4ff&fontAlignY=45&desc=AI%20Equity%20Research%20Platform%20%E2%80%A2%20Indian%20Markets&descAlignY=68&descSize=16&descColor=8b98b8&animation=twinkling&stroke=2dd4bf&strokeWidth=1" width="100%"/>

<p>
  <img src="https://img.shields.io/badge/Status-LIVE%20BETA-2dd4bf?style=for-the-badge&labelColor=0c1228"/>
  <img src="https://img.shields.io/badge/Version-v0.1-2dd4bf?style=for-the-badge&labelColor=0c1228"/>
  <img src="https://img.shields.io/badge/Infra-AWS%20ap--south--1-f5c842?style=for-the-badge&logo=amazonaws&logoColor=f5c842&labelColor=0c1228"/>
  <img src="https://img.shields.io/badge/Coverage-NSE%20%7C%20BSE-6366f1?style=for-the-badge&labelColor=0c1228"/>
</p>

</div>

---

## What is BharatAlpha?

BharatAlpha is an **AI-powered equity research platform built specifically for the Indian market**. It brings institutional-grade fundamental analysis, sector intelligence, and company deep-dives to every serious investor — powered by LLMs and multi-agent AI.

Part of **[NexAlpha](https://legitscarf.github.io/nexalpha.github.io/)** — the AI trading and research ecosystem for Indian financial markets.

---

## How It Works

```
User Query / Company Name
          │
          ▼
┌──────────────────────────────────────────────────────┐
│               BharatAlpha Research Engine            │
│                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ Fundamental │  │   Sector    │  │  Sentiment  │  │
│  │  Analyst    │  │  Analyst    │  │  Analyst    │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                         │                            │
│                         ▼                            │
│              ┌─────────────────────┐                 │
│              │  Research Synthesis │                 │
│              │  Agent              │                 │
│              └─────────────────────┘                 │
└──────────────────────────────────────────────────────┘
          │
          ▼
  Structured Research Report
```

| Agent | Role |
|:------|:-----|
| **Fundamental Analyst** | Revenue, margins, debt, valuations, ratios |
| **Sector Analyst** | Industry trends, competitive positioning, tailwinds |
| **Sentiment Analyst** | News, management commentary, analyst consensus |
| **Synthesis Agent** | Compiles inputs into a structured research report |

---

## Tech Stack

<div align="center">

![LLMs](https://img.shields.io/badge/LLMs-0c1228?style=for-the-badge&logo=openai&logoColor=2dd4bf)
![RAG](https://img.shields.io/badge/RAG%20Pipelines-0c1228?style=for-the-badge&logoColor=6366f1)
![Python](https://img.shields.io/badge/Python-0c1228?style=for-the-badge&logo=python&logoColor=3776ab)
![Streamlit](https://img.shields.io/badge/Streamlit-0c1228?style=for-the-badge&logo=streamlit&logoColor=ff4b4b)
![AWS EC2](https://img.shields.io/badge/AWS%20EC2-0c1228?style=for-the-badge&logo=amazonaws&logoColor=f5c842)
![Jenkins](https://img.shields.io/badge/Jenkins-0c1228?style=for-the-badge&logo=jenkins&logoColor=d33833)

</div>

---

## Infrastructure

```yaml
cloud        : AWS ap-south-1 (Mumbai)
compute      : EC2 with Application Load Balancer
ci_cd        : Jenkins + GitHub Webhooks
data_sources : NSE · BSE · Annual Reports · News feeds
ai_stack     : LLMs + RAG + Multi-Agent Orchestration
security     : IAM roles · Environment isolation
```

---

## Key Features

- **India-first design** — built around NSE/BSE data, Indian accounting standards, and local market context
- **Multi-agent research** — specialised agents handle fundamental, sector, and sentiment analysis in parallel
- **RAG-powered insights** — retrieval-augmented generation over annual reports, filings, and news
- **Structured reports** — clean, actionable output covering valuation, risks, and investment thesis
- **Production infrastructure** — 24/7 deployment on AWS with Jenkins CI/CD

---

## Status & Roadmap

| Milestone | Status |
|:----------|:------:|
| Core research agent architecture | ✅ Done |
| AWS production deployment | ✅ Done |
| Annual report ingestion (RAG) | ✅ Done |
| NSE/BSE data integration | ✅ Done |
| V2 — Portfolio tracking | 🔄 In Progress |
| V2 — Screener with AI scoring | 🔄 In Progress |
| Earnings call analysis | 📋 Planned |

---

<div align="center">

[![Visit BharatAlpha](https://img.shields.io/badge/Visit%20BharatAlpha-Live%20App-2dd4bf?style=for-the-badge&labelColor=0c1228)](http://bharatalpha-alb-97091621.ap-south-1.elb.amazonaws.com/)
&nbsp;
[![NexAlpha](https://img.shields.io/badge/NexAlpha-Website-f5c842?style=for-the-badge&labelColor=0c1228)](https://legitscarf.github.io/nexalpha.github.io/)
&nbsp;
[![Built By](https://img.shields.io/badge/Built%20by-Arpan%20Mallik-6366f1?style=for-the-badge&labelColor=0c1228)](https://github.com/legitscarf)

<br/>

> ⚠️ **Beta Notice:** BharatAlpha v0.1 is in active development. Research outputs are AI-generated and do not constitute financial advice. Always do your own due diligence.

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:070b18,50:0c1228,100:0a2a24&height=80&section=footer" width="100%"/>

</div>
