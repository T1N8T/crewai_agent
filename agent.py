
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import csv
import os 
from dotenv import load_dotenv
import urllib.request as libreq
import urllib.parse as parse
import xml.etree.ElementTree as ET



try:
    # Newer docs often show this path.
    from google.adk.agents.llm_agent import Agent  # type: ignore
except Exception:  # pragma: no cover
    from google.adk.agents import Agent  # type: ignore


from google.adk.models.lite_llm import LiteLlm 

# ==========================================
# DEFINICIÓN DE TOOLS 
# ==========================================

def search_arxiv_abstracts(topic :str) -> Dict[str, str]:
    #Search in ArXiv's API top relevant papers about CrewAI
    #and return a dictionary with
    #key: ArXiv ID
    #value: Abstract

    maxResults = 3
    res = {}

    sortBy = "relevance" #other options are "lastUpdatedDate","submittedDate"
    searchQuery = "all:CrewAI+AND+all:" + parse.quote(topic)
    link = f"http://export.arxiv.org/api/query?search_query={searchQuery}&sortBy={sortBy}&start=0&max_results={maxResults}" 

    try:
        with libreq.urlopen(link) as url:
            r = url.read()
        
        response = ET.fromstring(r)
        ns = {'atom': 'http://www.w3.org/2005/Atom'} #API's namespace

        
        for entry in response.findall('atom:entry',ns):
                
                abstract = entry.find("atom:summary",ns).text.replace('\n', ' ')
                id_url = entry.find("atom:id",ns).text
                paper_id = id_url.split("/")[-1] 

                res[paper_id] = f"ABSTRACT: {abstract}"
        
        if not res:
             return {"error": "No papers found for this topic"}
        else:
             return res
        
    except Exception as e:
        return {"Error": f"{e}"}


def generate_json():
    return 0

def generate_pdf():
    return 0


# ---------------------------
# Root agent
# ---------------------------
load_dotenv()
api_key = os.getenv("POLI_API_KEY")
api_base = os.getenv("POLI_API_BASE")

root_agent = Agent(
    # Pick a model you have configured (Gemini via GOOGLE_API_KEY, or via Vertex).
    # You can also route via LiteLLM if your environment is set up that way.
    #model="gemini-3-flash-preview",
    
    model = LiteLlm(model="openai/gpt-oss-120b", api_base=api_base, api_key=api_key),

    name="root_agent",
    description=(
        "Planifica una salida sencilla (2 opciones) en función del tiempo, preferencia y presupuesto, "
        "usando tools para fundamentar la respuesta."
    ),
    instruction=(
        "Eres un planificador de salidas. SIEMPRE debes fundamentarte en herramientas.\n"
        "Pasos: (1) llama a get_weather(city).\n"
        "(2) decide la categoría (SOLO entre estas: museo, outdoor, ocio): en funcion del tiempo que haga, por ejemplo si llueve mejor ir a un museo\n"
        "(3) llama a search_places(city, category) y elige hasta 2 lugares.\n"
        "(4) llama a estimate_cost con los nombres seleccionados.\n"
        "(5) responde en español con: categoría elegida, tiempo (resumen), 2 planes y coste total, "
        "sin inventar lugares fuera de la tool."
    ),
    tools=[],
)
