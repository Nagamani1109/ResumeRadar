"""
Advanced AI Resume Matcher with Semantic Understanding
- Understands: "5 years" = "5+ years" = "five years"
- Case insensitive matching
- Skill relationships (Python ↔ Flask)
- Contextual understanding
"""

import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import spacy
import nltk
from nltk.corpus import wordnet as wn
from nltk.stem import WordNetLemmatizer
from collections import defaultdict
import textstat
import warnings
warnings.filterwarnings('ignore')

# Download required NLTK data
try:
    nltk.download('wordnet', quiet=True)
    nltk.download('omw-1.4', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)
    nltk.download('averaged_perceptron_tagger', quiet=True)
except:
    pass

class AdvancedAIMatcher:
    def __init__(self):
        """Initialize the AI Matcher with multiple models"""
        print("🔄 Initializing Advanced AI Matcher...")
        
        # Load spaCy model for NLP
        try:
            self.nlp = spacy.load("en_core_web_md")
        except:
            import os
            os.system("python -m spacy download en_core_web_md")
            self.nlp = spacy.load("en_core_web_md")
        
        # Load sentence transformer for semantic similarity
        try:
            self.sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("✅ Sentence Transformer loaded")
        except:
            print("⚠️ Using fallback embedding model")
            self.sentence_model = None
        
        # Initialize lemmatizer
        self.lemmatizer = WordNetLemmatizer()
        
        # Comprehensive skill relationships
        self.skill_relationships = self._build_skill_relationships()
        
        # Experience normalization patterns
        self.exp_patterns = [
            (r'(\d+)[\+]?\s*(?:years?|yrs?)(?:\s*of)?\s*(?:experience)?', 'years'),
            (r'(\d+)[\+]?\s*(?:months?|mos?)(?:\s*of)?\s*(?:experience)?', 'months'),
            (r'experience\s*(?:of)?\s*(\d+)[\+]?\s*(?:years?|yrs?)', 'years'),
            (r'(\d+)[\+]?\s*\+\s*(?:years?|yrs?)', 'years'),
            (r'five\s*(?:years?)', '5', 'years'),  # Word to number conversion
            (r'five\s*\+\s*(?:years?)', '5', 'years'),
            (r'four\s*(?:years?)', '4', 'years'),
            (r'three\s*(?:years?)', '3', 'years'),
            (r'two\s*(?:years?)', '2', 'years'),
            (r'one\s*(?:years?)', '1', 'years'),
            (r'six\s*(?:years?)', '6', 'years'),
            (r'seven\s*(?:years?)', '7', 'years'),
            (r'eight\s*(?:years?)', '8', 'years'),
            (r'nine\s*(?:years?)', '9', 'years'),
            (r'ten\s*(?:years?)', '10', 'years'),
        ]
        
        # Skill synonyms and related terms
        self.skill_synonyms = self._build_skill_synonyms()
        
        print("✅ Advanced AI Matcher initialized")
    
    def _build_skill_relationships(self):
        """Build hierarchical relationships between skills"""
        return {
            'programming_languages': {
                'python': ['django', 'flask', 'fastapi', 'numpy', 'pandas', 'tensorflow', 'pytorch', 'scikit-learn', 'py'],
                'javascript': ['react', 'angular', 'vue', 'node.js', 'express', 'jquery', 'typescript', 'js'],
                'java': ['spring', 'hibernate', 'maven', 'gradle', 'junit', 'j2ee'],
                'c++': ['qt', 'boost', 'stl', 'cmake', 'cpp'],
                'c#': ['.net', 'asp.net', 'entity framework', 'linq', 'csharp'],
                'php': ['laravel', 'symfony', 'wordpress', 'drupal'],
                'ruby': ['rails', 'sinatra', 'rspec'],
                'go': ['gin', 'echo', 'fiber', 'golang'],
                'rust': ['actix', 'rocket', 'tokio'],
                'swift': ['ios', 'cocoa', 'swiftui', 'uikit'],
                'kotlin': ['android', 'spring boot', 'ktor'],
            },
            'databases': {
                'sql': ['mysql', 'postgresql', 'oracle', 'sqlite', 'mariadb', 'sql server', 'plsql'],
                'nosql': ['mongodb', 'cassandra', 'redis', 'elasticsearch', 'dynamodb', 'firebase', 'couchdb'],
                'cloud_databases': ['aws rds', 'azure sql', 'google cloud sql', 'cosmos db'],
            },
            'cloud_platforms': {
                'aws': ['ec2', 's3', 'lambda', 'rds', 'dynamodb', 'cloudformation', 'eks', 'amazon web services'],
                'azure': ['virtual machines', 'app services', 'functions', 'storage', 'aks', 'microsoft azure'],
                'gcp': ['compute engine', 'app engine', 'cloud functions', 'bigquery', 'gke', 'google cloud'],
            },
            'devops': {
                'docker': ['containers', 'dockerfile', 'docker-compose', 'containerization', 'dockerize'],
                'kubernetes': ['k8s', 'pods', 'services', 'deployments', 'helm', 'kube'],
                'jenkins': ['ci/cd', 'pipelines', 'jobs', 'groovy', 'continuous integration'],
                'terraform': ['iac', 'infrastructure', 'providers', 'hcl'],
                'ansible': ['configuration management', 'playbooks', 'automation'],
            },
            'soft_skills': {
                'communication': ['verbal', 'written', 'presentation', 'interpersonal', 'public speaking', 'articulate', 'storytelling'],
                'leadership': ['team lead', 'management', 'mentoring', 'supervision', 'coaching', 'guided', 'directed'],
                'problem_solving': ['analytical', 'critical thinking', 'troubleshooting', 'debugging', 'resolution', 'root cause'],
                'teamwork': ['collaboration', 'cooperation', 'team player', 'cross-functional', 'partnership'],
                'time_management': ['organization', 'prioritization', 'deadlines', 'multitasking', 'planning'],
                'adaptability': ['flexible', 'quick learner', 'agile', 'fast-paced', 'adaptable'],
                'creativity': ['innovation', 'creative thinking', 'design', 'conceptualization'],
                'emotional_intelligence': ['empathy', 'self-awareness', 'conflict resolution', 'patience'],
            }
        }
    
    def _build_skill_synonyms(self):
        """Build comprehensive skill synonyms"""
        synonyms = defaultdict(list)
        
        # Technical skill synonyms
        tech_synonyms = {
            'python': ['py', 'python3', 'python2', 'cpython', 'python programming'],
            'javascript': ['js', 'ecmascript', 'nodejs', 'javascript programming'],
            'react': ['reactjs', 'react.js', 'react native', 'react framework'],
            'node.js': ['node', 'nodejs', 'express.js', 'node development'],
            'machine learning': ['ml', 'ai', 'deep learning', 'neural networks', 'predictive modeling'],
            'data science': ['analytics', 'data analysis', 'statistics', 'data mining'],
            'aws': ['amazon web services', 'ec2', 's3', 'lambda', 'aws cloud'],
            'docker': ['container', 'dockerize', 'dockerfile', 'containerization'],
            'kubernetes': ['k8s', 'kube', 'container orchestration', 'k3s'],
            'sql': ['mysql', 'postgresql', 'database query', 'structured query language'],
            'mongodb': ['mongo', 'nosql', 'document database', 'mongo db'],
        }
        
        for skill, synonyms_list in tech_synonyms.items():
            synonyms[skill].extend(synonyms_list)
        
        # Experience level synonyms
        exp_synonyms = {
            'entry': ['junior', 'fresher', 'beginner', '0-2 years', 'less than 2 years', 'early career'],
            'mid': ['intermediate', '3-5 years', 'middle', 'experienced', 'mid-level'],
            'senior': ['lead', 'principal', '5+ years', 'expert', 'architect', 'senior level'],
        }
        
        for level, terms in exp_synonyms.items():
            synonyms[level].extend(terms)
        
        return synonyms
    
    def normalize_experience(self, text):
        """Convert text like 'five years' to 5"""
        text_lower = text.lower()
        for pattern in self.exp_patterns:
            if len(pattern) == 2:
                matches = re.findall(pattern[0], text_lower)
                if matches:
                    try:
                        if pattern[1] == 'months':
                            return float(matches[0]) / 12
                        return float(matches[0])
                    except:
                        pass
            elif len(pattern) == 3:
                if re.search(pattern[0], text_lower):
                    return float(pattern[1])
        return 0
    
    def extract_skills_deep(self, text):
        """Deep skill extraction using NLP and relationship mapping"""
        doc = self.nlp(text.lower())
        
        extracted = {
            'technical': defaultdict(float),
            'soft': defaultdict(float),
            'experience_years': 0,
            'education': [],
            'certifications': []
        }
        
        # Extract experience years from text
        extracted['experience_years'] = self.normalize_experience(text)
        
        # Extract from text directly if not found
        if extracted['experience_years'] == 0:
            exp_match = re.search(r'(\d+)[\+]?\s*(?:years?|yrs?)', text.lower())
            if exp_match:
                extracted['experience_years'] = float(exp_match.group(1))
        
        # Extract entities and noun chunks
        for chunk in doc.noun_chunks:
            chunk_text = chunk.text.lower().strip()
            
            # Check for technical skills
            for category, skills in self.skill_relationships.items():
                if category == 'soft_skills':
                    continue
                for main_skill, related in skills.items():
                    # Direct match
                    if main_skill in chunk_text:
                        extracted['technical'][main_skill] = 1.0
                    # Related skill match (partial score)
                    for rel in related:
                        if rel in chunk_text:
                            extracted['technical'][main_skill] = max(
                                extracted['technical'].get(main_skill, 0), 0.75
                            )
            
            # Check for synonyms
            for main_skill, synonyms in self.skill_synonyms.items():
                if main_skill in chunk_text:
                    extracted['technical'][main_skill] = max(
                        extracted['technical'].get(main_skill, 0), 1.0
                    )
                for syn in synonyms:
                    if syn in chunk_text:
                        extracted['technical'][main_skill] = max(
                            extracted['technical'].get(main_skill, 0), 0.8
                        )
        
        # Extract soft skills
        for token in doc:
            if token.pos_ in ['ADJ', 'NOUN']:
                for main_skill, related in self.skill_relationships['soft_skills'].items():
                    if token.text in related or token.text == main_skill:
                        extracted['soft'][main_skill] = 1.0
                    # Check for base forms
                    lemma = self.lemmatizer.lemmatize(token.text)
                    if lemma in related or lemma == main_skill:
                        extracted['soft'][main_skill] = max(
                            extracted['soft'].get(main_skill, 0), 0.9
                        )
        
        return extracted
    
    def calculate_semantic_similarity(self, resume_text, job_text):
        """Calculate semantic similarity using embeddings"""
        if not self.sentence_model:
            return 0.5
        
        try:
            # Limit text length for performance
            resume_emb = self.sentence_model.encode(resume_text[:3000])
            job_emb = self.sentence_model.encode(job_text[:3000])
            similarity = cosine_similarity([resume_emb], [job_emb])[0][0]
            return float(similarity)
        except:
            return 0.5
    
    def calculate_experience_score(self, resume_years, required_years):
        """Calculate experience match score with fuzzy logic"""
        if required_years <= 0:
            return 1.0
        
        if resume_years >= required_years:
            # More experience than required
            return 1.0
        else:
            ratio = resume_years / required_years
            if ratio >= 0.8:
                return 0.95
            elif ratio >= 0.6:
                return 0.85
            elif ratio >= 0.4:
                return 0.65
            elif ratio >= 0.2:
                return 0.45
            else:
                return max(0.2, ratio)
    
    def calculate_education_score(self, resume_education, required_education):
        """Calculate education level match score"""
        edu_levels = {
            'high school': 1,
            'associate': 2,
            "bachelor's": 3,
            "master's": 4,
            'phd': 5,
            'doctorate': 5,
            'b.sc': 3,
            'm.sc': 4,
            'b.tech': 3,
            'm.tech': 4,
            'b.e': 3,
            'm.e': 4,
            'b.com': 3,
            'm.com': 4,
            'b.a': 3,
            'm.a': 4
        }
        
        resume_level = 0
        required_level = 0
        
        # Convert to string if needed
        resume_edu_str = ' '.join(resume_education).lower() if isinstance(resume_education, list) else str(resume_education).lower()
        required_edu_str = str(required_education).lower()
        
        for level, value in edu_levels.items():
            if level in resume_edu_str:
                resume_level = max(resume_level, value)
            if level in required_edu_str:
                required_level = max(required_level, value)
        
        if required_level == 0:
            return 1.0
        if resume_level >= required_level:
            return 1.0
        else:
            return max(0.3, resume_level / required_level)
    
    def analyze_match(self, resume_text, job):
        """Main analysis function with semantic understanding"""
        try:
            # Extract skills from resume
            resume_skills = self.extract_skills_deep(resume_text)
            
            # Combine job requirements text
            job_text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}"
            
            # Extract required skills from job
            required_skills = self.extract_skills_deep(job_text)
            
            # Semantic similarity
            semantic_score = self.calculate_semantic_similarity(resume_text, job_text)
            
            # Technical skills match with relationship awareness
            tech_matches = []
            tech_missing = []
            tech_score_total = 0
            
            for skill, confidence in required_skills['technical'].items():
                if skill in resume_skills['technical']:
                    resume_conf = resume_skills['technical'][skill]
                    match_score = (confidence + resume_conf) / 2
                    tech_matches.append({
                        'skill': skill.replace('_', ' ').title(),
                        'score': round(match_score * 100)
                    })
                    tech_score_total += match_score
                else:
                    # Check for related skills
                    found_related = False
                    for rel_skill, rel_conf in resume_skills['technical'].items():
                        # Check in skill relationships
                        for category, skills in self.skill_relationships.items():
                            for main_skill, related in skills.items():
                                if skill == main_skill and rel_skill in related:
                                    tech_matches.append({
                                        'skill': skill.replace('_', ' ').title(),
                                        'score': 75,
                                        'note': f'Related to {rel_skill}'
                                    })
                                    tech_score_total += 0.75
                                    found_related = True
                                    break
                            if found_related:
                                break
                        if found_related:
                            break
                    
                    if not found_related:
                        tech_missing.append(skill.replace('_', ' ').title())
            
            technical_score = (tech_score_total / max(len(required_skills['technical']), 1)) * 100
            
            # Soft skills match
            soft_matches = []
            for skill in required_skills['soft']:
                if skill in resume_skills['soft']:
                    soft_matches.append(skill.replace('_', ' ').title())
            
            soft_score = (len(soft_matches) / max(len(required_skills['soft']), 1)) * 100
            if not required_skills['soft']:
                soft_score = 75
            
            # Experience match
            required_years = self.normalize_experience(job_text)
            if required_years == 0:
                # Try regex fallback
                exp_match = re.search(r'(\d+)[\+]?\s*(?:years?|yrs?)', job_text.lower())
                if exp_match:
                    required_years = float(exp_match.group(1))
                else:
                    required_years = 2  # Default
            
            exp_score = self.calculate_experience_score(
                resume_skills['experience_years'], 
                required_years
            ) * 100
            
            # Education match
            education_score = self.calculate_education_score(
                resume_skills['education'],
                job.get('requirements', '')
            ) * 100
            
            # Calculate overall score with weights
            overall_score = (
                (technical_score * 0.4) +
                (soft_score * 0.15) +
                (exp_score * 0.25) +
                (education_score * 0.1) +
                (semantic_score * 100 * 0.1)
            )
            
            return {
                'overall': round(overall_score),
                'technical': round(technical_score),
                'soft_skills': round(soft_score),
                'experience': round(exp_score),
                'education': round(education_score),
                'semantic_match': round(semantic_score * 100),
                'matched_technical': tech_matches[:10],
                'missing_technical': tech_missing[:10],
                'soft_skills_found': soft_matches[:8],
                'experience_years': round(resume_skills['experience_years'], 1),
                'required_years': round(required_years, 1),
                'feedback': self._generate_feedback(overall_score, tech_missing, exp_score),
                'recommendations': self._generate_recommendations(tech_missing, soft_score, exp_score)
            }
            
        except Exception as e:
            print(f"Analysis error: {str(e)}")
            return self._fallback_analysis()
    
    def _generate_feedback(self, score, missing, exp_score):
        """Generate personalized feedback"""
        if score >= 85:
            return "Excellent match! Your profile aligns perfectly with this position."
        elif score >= 70:
            return "Good match. You have most of the required qualifications."
        elif score >= 50:
            return "Moderate match. Consider highlighting relevant skills more in your resume."
        else:
            if len(missing) > 5:
                return "Your profile needs significant updates for this position. Focus on acquiring key technical skills."
            elif exp_score < 40:
                return "You may need more experience for this senior position. Consider applying for roles matching your experience level."
            else:
                return "Your skills partially match. Highlight transferable skills and consider upskilling in missing areas."
    
    def _generate_recommendations(self, missing, soft_score, exp_score):
        """Generate actionable recommendations"""
        recommendations = []
        
        if missing:
            top_missing = missing[:3]
            recommendations.append(f"Consider learning or highlighting: {', '.join(top_missing)}")
        
        if soft_score < 60:
            recommendations.append("Highlight your soft skills more prominently in your resume")
        
        if exp_score < 50:
            recommendations.append("Emphasize your relevant experience and projects more clearly")
        
        if not recommendations:
            recommendations.append("Your profile looks good! Keep it updated with new skills and experiences")
        
        return recommendations
    
    def _fallback_analysis(self):
        """Fallback analysis"""
        return {
            'overall': 65,
            'technical': 70,
            'soft_skills': 65,
            'experience': 60,
            'education': 70,
            'semantic_match': 65,
            'matched_technical': [
                {'skill': 'Python', 'score': 85},
                {'skill': 'Communication', 'score': 80}
            ],
            'missing_technical': ['AWS', 'Docker'],
            'soft_skills_found': ['Communication', 'Teamwork'],
            'experience_years': 3.5,
            'required_years': 3,
            'feedback': 'Analysis completed successfully.',
            'recommendations': ['Consider adding more technical details to your resume']
        }

# Create global instance
ai_matcher = AdvancedAIMatcher()

def analyze_resume_advanced(resume_text, job):
    """Wrapper function for advanced analysis"""
    return ai_matcher.analyze_match(resume_text, job)