# Pharma QA & Regulatory Compliance Assistant

A ChatGPT-style AI assistant built for pharmaceutical Quality Assurance (QA) and Quality Control (QC) teams. It helps quality engineers instantly look up manufacturing rules from Standard Operating Procedures (SOPs), check live batch testing results in plain English, and download audit checklists as PDFs—without making up answers.

## What Problem Does This Solve?
In medicine manufacturing, QA teams spend hours manually cross-checking thick PDF rulebooks (SOPs) against factory batch testing databases before approving a medicine batch for release. 

Standard AI chatbots often guess numbers or cannot connect to live company databases. This assistant solves both problems by:
1. **Answering SOP questions with exact PDF page numbers** so every rule can be verified in seconds.
2. **Checking live batch test records in plain English** (no SQL knowledge required).
3. **Generating downloadable PDF audit checklists** combining SOP rules and flagged batches.

## How It Works (Simple Flow)
User asks a question in the Chat UI
               │
               ▼
   Smart Router ("Traffic Cop")
   ├──► Policy / Rule Question  ──► Searches SOP PDFs & replies with exact [File | Page] citations
   ├──► Batch / Lab Data Query  ──► Safely reads the SQLite batch database & shows results
   └──► Audit / Checklist Task  ──► Combines SOP rules + failed batches & creates a PDF report
