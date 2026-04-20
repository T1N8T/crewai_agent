
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import csv
import os 
import json
from dotenv import load_dotenv
import urllib.request as libreq
import urllib.parse as parse
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from fpdf import FPDF


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

                title = entry.find("atom:title",ns).text.replace('\n', ' ').strip()
                year = entry.find("atom:published", ns).text[:4]
                authors_list = [author.find('atom:name', ns).text for author in entry.findall('atom:author', ns)]
                authors = ", ".join(authors_list)

                res[paper_id] = f"TITLE: {title} | AUTHORS: {authors} | YEAR: {year} | ABSTRACT: {abstract}" #We are also taking, title, authors and year now to build bibliography later
        
        if not res:
             return {"error": "No papers found for this topic"}
        else:
             return res
        
    except Exception as e:
        return {"Error": f"{e}"}
    
def read_section(paperID: str, sectionKW: str) -> str:
    # Fetches the HTML version of an ArXiv paper and extracts the text of a specific section 
    url = f"https://ar5iv.labs.arxiv.org/html/{paperID}"

    try:
        req = libreq.Request(url, headers={'User-Agent': 'Mozilla/5.0'}) # We use headers to avoid bans
        with libreq.urlopen(req) as response:
            html = response.read()
        
        soup = BeautifulSoup(html, 'html.parser')

        headers = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])

        targetHeader = None
        for header in headers: 
            if sectionKW.lower() in header.get_text().lower():
                targetHeader = header
                break

        if not targetHeader:
            #In order to reduce token usage we are just taking the first words of the section
            sections = [" ".join(h.get_text().strip().split()[:4]) for h in headers if h.get_text().strip()]
            
            #To check there are not two equal named sections
            sections_unicas = list(dict.fromkeys(sections)) 
            sections_txt = ", ".join(sections_unicas)
            

            return f"Error: Section '{sectionKW}' not found in this paper. Available sections are: {sections_txt}. Please call this tool again using one of these exact section names."    

        content = []
        targetLevel = int(targetHeader.name[1])

        for sibling in targetHeader.find_next_siblings():
            if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                siblingLevel = int(sibling.name[1])

                if siblingLevel <= targetLevel:
                    break
                else:
                    content.append(f"\n--- {sibling.get_text().strip()} ---")

            else:
                text = sibling.get_text().strip()
                if text:  
                    content.append(text)
                
        res = " ".join(content)

        if not res:
            return f"Error: The section '{sectionKW}' does not have text."

        words = res.split()
        if len(words) > 800:
            res = " ".join(words[:800]) + "... [Text truncated to save context memory, try again with a more specific section?]"

        return f"SECTION '{sectionKW.upper()}' CONTENT:\n{res}"
    
    except Exception as e:
        return f"Error: {e}"


def generate_pdf(title:str, sections: dict, bibliography:str) -> str:

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    #TITLE
    pdf.set_font("Arial", 'B', 24) #title font, bold, size
    pdf.cell(0, 20, title, ln=True, align='C')
    pdf.ln(10)

    #BODY
    for name, text in sections.items():
        # Section's title
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, name, ln=True)
        pdf.ln(2)
        
        # Text
        pdf.set_font("Times", size=12)
        pdf.multi_cell(0, 8, text)
        pdf.ln(5) 

    #Bibliography
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Bibliografía", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Times", size=10) 
    pdf.multi_cell(0, 6, bibliography)

    #Export
    try:
        os.makedirs("output", exist_ok=True)
        name =  "".join([c if c.isalnum() else "_" for c in title])
        path = f"output/informe_{name}.pdf"
        pdf.output(path)
        return f"SUCCESS: PDF generated successfully at {path}"
    except Exception as e:
        return f"ERROR: Failed to generate PDF: {e}"

def generate_json(title: str, sections_list: List[Dict[str, Any]], total_words: int, num_references: int, pdf_path: str) -> str:
    # Generates a JSON file with metadata about the report, including title, sections, word counts, references, and PDF path.
    # Create the dictionary structure for the report metadata from input parameters
    report_data = {
        "title": title,                               # string: The report title
        "sections": sections_list,                    # array<object>: [{name, word_count}, ...]
        "total_words": total_words,                   # integer: Sum of all section words
        "num_sections": len(sections_list),           # integer: Total section count
        "num_references": num_references,             # integer: Bibliography count
        "pdf_path": pdf_path                          # string: Path to the generated PDF file
    }
    
    try:
        os.makedirs("output", exist_ok=True)
        # Create a unique filename for the JSON metadata
        safe_title = "".join([c if c.isalnum() else "_" for c in title])
        # Make sure no spaces or special characters are in the filename
        json_path = f"output/informe_{safe_title}.json"
        
        # Write the data to a file using UTF-8 encoding and 4-space indentation
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=4)
        # Exception handling to catch and report any errors during file writing   
        return f"SUCCESS: JSON metadata created at {json_path}"
    except Exception as e:
        return f"ERROR: JSON generation failed: {e}"




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
    role="Senior Academic Researcher and Scientific Writer",
    goal="Investigate complex topics on ArXiv, extract real empirical knowledge, format it into a PDF, and structure the output in JSON for automated evaluation.",
    backstory=(
        "You are an elite researcher specializing in reviewing scientific literature "
        "on ArXiv. You are extremely meticulous: you NEVER invent or hallucinate data. "
        "If you make a claim, it is because you have read it directly from a paper using your tools. "
        "Furthermore, you are an expert data engineer capable of structuring information "
        "with huge precision so it can be easily parsed and evaluated by automated systems."
    ),
    instruction=("""You are an autonomous agent. To successfully complete your task and achieve the maximum score, you MUST STRICTLY follow this sequential 5-phase workflow:
                 
        PHASE 1: RESEARCH (Tool: search_arxiv_abstracts)
            1. Call the 'search_arxiv_abstracts' tool with the given topic to retrieve the most relevant papers and their abstracts.
            2. It is mandatory that you base your report on at least 3 real papers. Keep the Title, Author, Year, and ID (paper_id) of each one in your working memory. However, if you find less than 3 (it does not mind whether they arerelevant or not) papers, you can proceed with the ones you have and tell the user he should try again with other words, but never with zero. If no papers are found, you should end the process and report that no information is available on this topic. In that case, you should also suggest the user to try again with other keywords, and if you detect any error in users' input, you can suggest the user to correct it.
                 
        PHASE 2: DEEP EXTRACTION (Tool: read_section)
            1. Do not rely solely on the abstract. Call 'read_section' with every exact 'paper_id' obtained in Phase 1 and the name of the section you think is the most relevant to the topic. You can also explore other sections if you think they are interesting, but it is not mandatory. The more sections you read within reasonable limits (this means they have to be actually relevant), the better, as long as they really fit into the topic and you do not run out of context memory.
            2. If the tool returns an error stating that the section does not exist, CAREFULLY READ the list of available sections provided in the error message. Call the tool again using one of the suggested names from that list.
            3. You must NEVER invent or hallucinate technical information. All content must come exclusively from the extracted texts.
        
        PHASE 3: WRITING AND STRUCTURING (Internal memory, no tool)
            1. Sinthesize the information you have read and organize your written report inside a Python dictionary, according to users' request and the following rules, where the key is the name of the section and the value is the content of that section.
            2. Choose a title for the report that reflects its content and is attractive for user.
            3. DICTIONARY STRUCTURE RULE: 
                - The first key must be exactly "Introduction".
                - Add between 2 and 5 intermediate keys for the body of the report.
                - The last key must be exactly "Conclusions".
            4. Calculate the total word count of the report, and keep this information in your working memory to be included in the JSON metadata later.
            5. Prepare a separate text string containing the Bibliography in APA format, using the metadata from Phase 1.

        PHASE 4: DELIVERABLE GENERATION (Tools: generate_pdf and generate_json)  
            1. Call 'generate_pdf' with: (1) the title, (2) the sections (this is the dictionary created in Phase 3), and (3) the bibliography to create a well-formatted PDF report.
            2. Call 'generate_json' with: (1) the title, (2) the same dictionary, (3) the number of references in the bibliography, and (4) the path to the generated PDF (which is ALWAYS specified in the return value of 'generate_pdf'), to create a structured JSON file with all this metadata.
        
        PHASE 5: FINAL RESPONSE & EVALUATION (Critical Directive)
        1. Once the previous phases are complete, write a message informing the user that the files have been successfully generated in the '/output' folder.
        2. CRITICAL FOR YOUR EVALUATION: At the very end of your text message to the user, you MUST print a code block containing the complete and exact JSON that was returned by the 'generate_json' tool. Without this, the task will be considered a failure.
                 
        """
    ),
    tools=[search_arxiv_abstracts, read_section, generate_pdf, generate_json],
    allow_delegation=False,
    verbose=True, # This helps to see what the agent thinks step by step
    system_template=instruction
)
