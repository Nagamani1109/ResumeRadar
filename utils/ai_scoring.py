# utils/ai_scoring.py - Advanced AI Matching
from sentence_transformers import SentenceTransformer, util
import numpy as np
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import spacy
from collections import Counter

# Load models (cached)
_model = None
_nlp = None

def get_model():
    """Get or load the sentence transformer model"""
    global _model
    if _model is None:
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model

def get_nlp():
    """Get or load spaCy model"""
    global _nlp
    if _nlp is None:
        _nlp = spacy.load('en_core_web_sm')
    return _nlp

def preprocess_text(text):
    """Advanced text preprocessing"""
    text = text.lower()
    text = re.sub(r'[^\w\s@.]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_skills(text):
    """Extract skills using NLP"""
    nlp = get_nlp()
    doc = nlp(text)
    
    # Common tech skills database
    tech_skills = {
        'python', 'java', 'javascript', 'typescript', 'react', 'angular', 'vue',
        'node.js', 'express', 'django', 'flask', 'fastapi', 'spring', 'asp.net',
        'mongodb', 'mysql', 'postgresql', 'redis', 'elasticsearch',
        'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'terraform',
        'git', 'jenkins', 'ci/cd', 'pytest', 'junit', 'selenium',
        'tensorflow', 'pytorch', 'scikit-learn', 'pandas', 'numpy',
        'html', 'css', 'sass', 'tailwind', 'bootstrap',
        'rest', 'graphql', 'grpc', 'websockets',
        'oop', 'design patterns', 'microservices', 'serverless',
        'agile', 'scrum', 'kanban', 'jira', 'confluence'
    }
    
    # Extract entities and match with skills database
    entities = [ent.text.lower() for ent in doc.ents if ent.label_ in ['ORG', 'PRODUCT', 'SKILL']]
    words = [token.text.lower() for token in doc if token.pos_ in ['NOUN', 'PROPN', 'ADJ']]
    
    # Find matching skills
    found_skills = set()
    for word in words + entities:
        if word in tech_skills:
            found_skills.add(word)
        # Check for multi-word skills
        for skill in tech_skills:
            if skill in word and len(skill) > 3:
                found_skills.add(skill)
    
    return list(found_skills)

def calculate_match_score(job_description, resume_text):
    """
    Calculate comprehensive match score using semantic similarity
    Returns score from 0-100
    """
    # Preprocess texts
    job_clean = preprocess_text(job_description)
    resume_clean = preprocess_text(resume_text)
    
    # Get embeddings and calculate semantic similarity
    model = get_model()
    embeddings = model.encode([job_clean, resume_clean])
    semantic_similarity = float(util.cos_sim(embeddings[0], embeddings[1])[0][0])
    
    # Extract skills
    job_skills = extract_skills(job_description)
    resume_skills = extract_skills(resume_text)
    
    # Calculate skill match
    if job_skills:
        matched_skills = set(job_skills) & set(resume_skills)
        skill_match = len(matched_skills) / len(job_skills)
    else:
        skill_match = 0.5
    
    # Calculate TF-IDF similarity
    vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
    try:
        tfidf_matrix = vectorizer.fit_transform([job_clean, resume_clean])
        tfidf_similarity = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])
    except:
        tfidf_similarity = 0.5
    
    # Weighted combination
    final_score = (
        semantic_similarity * 0.5 +  # Semantic understanding (50%)
        skill_match * 0.3 +          # Skills match (30%)
        tfidf_similarity * 0.2       # Keyword match (20%)
    ) * 100
    
    # Ensure score is between 0-100
    return max(0, min(100, round(final_score, 2)))

def analyze_skills(job_description, resume_text):
    """
    Detailed skill analysis with scores for different categories
    """
    job_skills = extract_skills(job_description)
    resume_skills = extract_skills(resume_text)
    
    # Categorize skills
    categories = {
        'programming_languages': ['python', 'java', 'javascript', 'c++', 'c#', 'ruby', 'php', 'swift', 'kotlin', 'go', 'rust'],
        'frameworks': ['react', 'angular', 'vue', 'django', 'flask', 'fastapi', 'spring', 'express', 'rails', 'laravel'],
        'databases': ['mongodb', 'mysql', 'postgresql', 'redis', 'elasticsearch', 'cassandra', 'dynamodb'],
        'devops': ['docker', 'kubernetes', 'aws', 'azure', 'gcp', 'jenkins', 'terraform', 'ansible'],
        'soft_skills': ['leadership', 'communication', 'teamwork', 'problem solving', 'analytical', 'adaptability']
    }
    
    analysis = {}
    for category, skills in categories.items():
        job_cat_skills = [s for s in job_skills if s in skills]
        resume_cat_skills = [s for s in resume_skills if s in skills]
        
        if job_cat_skills:
            matched = set(job_cat_skills) & set(resume_cat_skills)
            score = len(matched) / len(job_cat_skills) * 100
        else:
            score = 100
        
        analysis[category] = {
            'score': round(score, 2),
            'matched': list(matched) if 'matched' in locals() else [],
            'missing': list(set(job_cat_skills) - set(resume_cat_skills)) if job_cat_skills else []
        }
    
    # Overall score
    all_scores = [v['score'] for v in analysis.values()]
    overall = sum(all_scores) / len(all_scores) if all_scores else 0
    
    return {
        'overall': round(overall, 2),
        'categories': analysis,
        'all_job_skills': job_skills,
        'all_resume_skills': resume_skills,
        'matched_skills': list(set(job_skills) & set(resume_skills)),
        'missing_skills': list(set(job_skills) - set(resume_skills))
    }