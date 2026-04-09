# utils/resume_parser.py - Resume Parsing
import fitz  # PyMuPDF
from docx import Document
import spacy
import re
from datetime import datetime

_nlp = None

def get_nlp():
    """Get or load spaCy model"""
    global _nlp
    if _nlp is None:
        _nlp = spacy.load('en_core_web_sm')
    return _nlp

def parse_pdf(filepath):
    """Extract text from PDF"""
    text = ""
    try:
        doc = fitz.open(filepath)
        for page in doc:
            text += page.get_text()
    except Exception as e:
        print(f"PDF parsing error: {e}")
    return text

def parse_docx(filepath):
    """Extract text from DOCX"""
    text = ""
    try:
        doc = Document(filepath)
        for para in doc.paragraphs:
            text += para.text + "\n"
    except Exception as e:
        print(f"DOCX parsing error: {e}")
    return text

def extract_education(text):
    """Extract education information"""
    nlp = get_nlp()
    doc = nlp(text)
    
    education_keywords = ['bachelor', 'master', 'phd', 'b.tech', 'm.tech', 'b.e.', 'm.e.', 
                          'b.sc', 'm.sc', 'b.a.', 'm.a.', 'diploma', 'degree', 'university',
                          'college', 'institute', 'school']
    
    education = []
    sentences = list(doc.sents)
    
    for sent in sentences:
        sent_lower = sent.text.lower()
        if any(keyword in sent_lower for keyword in education_keywords):
            # Extract degree and institution
            degree = None
            institution = None
            
            for token in sent:
                if token.ent_type_ == 'ORG' and len(token.text) > 3:
                    institution = token.text
                if token.text.lower() in ['bachelor', 'master', 'phd', 'b.tech', 'm.tech']:
                    degree = token.text
            
            education.append({
                'text': sent.text.strip(),
                'degree': degree,
                'institution': institution
            })
    
    return education

def extract_experience(text):
    """Extract work experience"""
    nlp = get_nlp()
    doc = nlp(text)
    
    experience = []
    experience_keywords = ['experience', 'worked', 'work', 'job', 'position', 'role',
                          'company', 'organization', 'employer', 'employment']
    
    # Date patterns
    date_pattern = r'\b(19|20)\d{2}\b'
    years = re.findall(date_pattern, text)
    
    sentences = list(doc.sents)
    for sent in sentences:
        sent_lower = sent.text.lower()
        if any(keyword in sent_lower for keyword in experience_keywords):
            # Look for company names
            company = None
            for token in sent:
                if token.ent_type_ == 'ORG' and len(token.text) > 2:
                    company = token.text
            
            experience.append({
                'text': sent.text.strip(),
                'company': company,
                'years': years if years else []
            })
    
    return experience

def parse_resume(filepath):
    """Main resume parsing function"""
    # Extract text based on file type
    if filepath.lower().endswith('.pdf'):
        text = parse_pdf(filepath)
    elif filepath.lower().endswith('.docx'):
        text = parse_docx(filepath)
    elif filepath.lower().endswith('.txt'):
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
    else:
        text = ""
    
    # Use spaCy for NLP
    nlp = get_nlp()
    doc = nlp(text[:10000])  # Limit for performance
    
    # Extract entities
    entities = {
        'skills': [],
        'organizations': [],
        'people': [],
        'dates': [],
        'locations': []
    }
    
    for ent in doc.ents:
        if ent.label_ == 'ORG':
            entities['organizations'].append(ent.text)
        elif ent.label_ == 'PERSON':
            entities['people'].append(ent.text)
        elif ent.label_ == 'DATE':
            entities['dates'].append(ent.text)
        elif ent.label_ == 'GPE':
            entities['locations'].append(ent.text)
    
    # Extract education and experience
    education = extract_education(text)
    experience = extract_experience(text)
    
    # Extract skills using AI scoring module
    from .ai_scoring import extract_skills
    skills = extract_skills(text)
    
    # Calculate stats
    words = text.split()
    word_count = len(words)
    char_count = len(text)
    
    return {
        'text': text[:5000],  # Store first 5000 chars
        'full_text': text,
        'word_count': word_count,
        'char_count': char_count,
        'entities': {
            'skills': skills,
            'organizations': list(set(entities['organizations']))[:10],
            'education': education,
            'experience': experience,
            'dates': list(set(entities['dates']))[:10],
            'locations': list(set(entities['locations']))[:5]
        },
        'summary': {
            'estimated_experience_years': len(re.findall(r'\b(19|20)\d{2}\b', text)) // 2,
            'has_email': bool(re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)),
            'has_phone': bool(re.search(r'[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}', text))
        }
    }