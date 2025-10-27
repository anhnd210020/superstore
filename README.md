# README

## Abstract

This project implements an automated Business Intelligence (BI) system that enables users to ask questions in natural language and receive concise, data-driven insights. The system operates through a streamlined pipeline in which the user’s question is first converted into an SQL query by a Large Language Model (LLM) using a predefined database schema, then executed on a structured DataMart to retrieve relevant data. The retrieved data is subsequently summarized by the LLM into short, human-readable insights. All of these steps are handled through a single API endpoint, allowing users to obtain business insights without needing any knowledge of SQL or data analysis. The system is built with a modular architecture that clearly separates the API layer, processing pipeline, LLM interaction, and database access, making it clean, maintainable, and easy to extend.

## Results

## File Organization
```text
superstore/
├─ app/
│  ├─ api/
│  │  └─ app.py
│  ├─ dataops/
│  │  └─ datamart_build.py
│  │  └─ kpi_compute.py
│  ├─ intents/
│  │  └─ query_engine.py   
│  ├─ llm/
│  │  └─ llm_client.py                     
│  └─ service/
│     └─ ask_pipeline.py          
├─ schema_catalog.json            
├─ artifacts/
│  └─ salesmart.db                
└─ requirements.txt               
```