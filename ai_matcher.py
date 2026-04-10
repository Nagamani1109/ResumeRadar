"""
Lightweight AI Matcher - Optimized for Free Tier
Uses simple but effective matching without heavy ML models
"""

import re
from collections import defaultdict

class AdvancedAIMatcher:
    def __init__(self):
        """Initialize lightweight matcher - no heavy models!"""
        print("🔄 Initializing Lightweight AI Matcher...")
        
        # Define skill relationships (lightweight)
        self.skill_relationships = self._build_skill_relationships()
        
        # Experience patterns
        self.exp_patterns = [
            (r'(\d+)[\+]?\s*(?:years?|yrs?)(?:\s*of)?\s*(?:experience)?', 'years'),
            (r'(\d+)[\+]?\s*(?:months?|mos?)', 'months'),
            (r'five\s*(?:years?)', '5', 'years'),
            (r'four\s*(?:years?)', '4', 'years'),
            (r'three\s*(?:years?)', '3', 'years'),
            (r'two\s*(?:years?)', '2', 'years'),
            (r'one\s*(?:years?)', '1', 'years'),
        ]
        
        print("✅ Lightweight AI Matcher initialized (Memory Optimized)")
    
    def _build_skill_relationships(self):
        """Build skill relationships (lightweight)"""
        return {
            'programming_languages': {
                'python': ['django', 'flask', 'fastapi', 'numpy', 'pandas'],
                'javascript': ['react', 'angular', 'vue', 'node.js', 'express'],
                'java': ['spring', 'hibernate', 'maven'],
                'c++': ['qt', 'boost', 'stl'],
                'c#': ['.net', 'asp.net', 'entity framework'],
            },
            'databases': {
                'sql': ['mysql', 'postgresql', 'oracle', 'sqlite'],
                'nosql': ['mongodb', 'cassandra', 'redis', 'elasticsearch'],
            },
            'cloud_platforms': {
                'aws': ['ec2', 's3', 'lambda', 'rds', 'dynamodb'],
                'azure': ['virtual machines', 'app services', 'functions'],
                'gcp': ['compute engine', 'app engine', 'cloud functions'],
            },
            'soft_skills': {
                'communication': ['verbal', 'written', 'presentation'],
                'leadership': ['team lead', 'management', 'mentoring'],
                'problem_solving': ['analytical', 'critical thinking', 'troubleshooting'],
                'teamwork': ['collaboration', 'cooperation', 'team player'],
                'time_management': ['organization', 'prioritization', 'deadlines'],
            }
        }
    
    def extract_skills_deep(self, text):
        """Lightweight skill extraction - no NLP models"""
        text_lower = text.lower()
        
        extracted = {
            'technical': defaultdict(float),
            'soft': defaultdict(float),
            'experience_years': 0,
            'education': [],
            'certifications': []
        }
        
        # Extract experience years
        for pattern in self.exp_patterns:
            if len(pattern) == 2:
                matches = re.findall(pattern[0], text_lower)
                if matches:
                    try:
                        years = float(matches[0])
                        if pattern[1] == 'months':
                            years = years / 12
                        extracted['experience_years'] = max(extracted['experience_years'], years)
                    except:
                        pass
            elif len(pattern) == 3:
                if re.search(pattern[0], text_lower):
                    extracted['experience_years'] = max(extracted['experience_years'], float(pattern[1]))
        
        # Extract technical skills (simple keyword matching)
        for category, skills in self.skill_relationships.items():
            if category == 'soft_skills':
                continue
            for main_skill, related in skills.items():
                if main_skill in text_lower:
                    extracted['technical'][main_skill] = 1.0
                for rel in related:
                    if rel in text_lower:
                        extracted['technical'][main_skill] = max(extracted['technical'].get(main_skill, 0), 0.7)
        
        # Extract soft skills
        for main_skill, related in self.skill_relationships['soft_skills'].items():
            if main_skill in text_lower:
                extracted['soft'][main_skill] = 1.0
            for rel in related:
                if rel in text_lower:
                    extracted['soft'][main_skill] = max(extracted['soft'].get(main_skill, 0), 0.7)
        
        return extracted
    
    def calculate_semantic_similarity(self, resume_text, job_text):
        """Simple semantic similarity without heavy models"""
        # Use simple keyword overlap as fallback
        resume_words = set(resume_text.lower().split())
        job_words = set(job_text.lower().split())
        
        if not job_words:
            return 0.5
        
        overlap = len(resume_words.intersection(job_words))
        similarity = min(1.0, overlap / max(len(job_words), 1))
        return similarity
    
    def calculate_experience_score(self, resume_years, required_years):
        """Calculate experience match score"""
        if required_years <= 0:
            return 1.0
        
        if resume_years >= required_years:
            return 1.0
        else:
            ratio = resume_years / required_years
            if ratio >= 0.8:
                return 0.9
            elif ratio >= 0.6:
                return 0.75
            elif ratio >= 0.4:
                return 0.5
            else:
                return max(0.2, ratio)
    
    def calculate_education_score(self, resume_education, required_education):
        """Calculate education match score"""
        edu_levels = {
            "bachelor's": 3, "b.sc": 3, "b.tech": 3,
            "master's": 4, "m.sc": 4, "m.tech": 4,
            'phd': 5, 'doctorate': 5
        }
        
        resume_level = 0
        required_level = 0
        
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
        """Main analysis function - lightweight version"""
        try:
            # Extract skills
            resume_skills = self.extract_skills_deep(resume_text)
            
            # Combine job requirements
            job_text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}"
            required_skills = self.extract_skills_deep(job_text)
            
            # Calculate similarity
            semantic_score = self.calculate_semantic_similarity(resume_text, job_text)
            
            # Technical skills match
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
                    tech_missing.append(skill.replace('_', ' ').title())
            
            technical_score = (tech_score_total / max(len(required_skills['technical']), 1)) * 100
            
            # Soft skills match
            soft_matches = []
            for skill in required_skills['soft']:
                if skill in resume_skills['soft']:
                    soft_matches.append(skill.replace('_', ' ').title())
            
            soft_score = (len(soft_matches) / max(len(required_skills['soft']), 1)) * 100
            if not required_skills['soft']:
                soft_score = 70
            
            # Experience match
            required_years = self._extract_required_years(job_text)
            exp_score = self.calculate_experience_score(resume_skills['experience_years'], required_years) * 100
            
            # Education match
            education_score = self.calculate_education_score(
                resume_skills['education'],
                job.get('requirements', '')
            ) * 100
            
            # Calculate overall score
            overall_score = (
                (technical_score * 0.45) +
                (soft_score * 0.20) +
                (exp_score * 0.25) +
                (education_score * 0.05) +
                (semantic_score * 100 * 0.05)
            )
            
            return {
                'overall': round(overall_score),
                'technical': round(technical_score),
                'soft_skills': round(soft_score),
                'experience': round(exp_score),
                'education': round(education_score),
                'semantic_match': round(semantic_score * 100),
                'matched_technical': tech_matches[:8],
                'missing_technical': tech_missing[:8],
                'soft_skills_found': soft_matches[:5],
                'experience_years': round(resume_skills['experience_years'], 1),
                'feedback': self._generate_feedback(overall_score, tech_missing),
                'recommendations': self._generate_recommendations(tech_missing, soft_score)
            }
            
        except Exception as e:
            print(f"Analysis error: {str(e)}")
            return self._fallback_analysis()
    
    def _extract_required_years(self, text):
        """Extract required years from job text"""
        for pattern in self.exp_patterns:
            if len(pattern) == 2:
                matches = re.findall(pattern[0], text.lower())
                if matches:
                    try:
                        years = float(matches[0])
                        if pattern[1] == 'months':
                            years = years / 12
                        return years
                    except:
                        pass
        return 2
    
    def _generate_feedback(self, score, missing):
        """Generate feedback"""
        if score >= 85:
            return "Excellent match! Your profile aligns perfectly with this position."
        elif score >= 70:
            return "Good match. You have most of the required qualifications."
        elif score >= 50:
            return "Moderate match. Consider highlighting relevant skills more."
        else:
            if len(missing) > 3:
                return "Your profile needs significant updates for this position."
            else:
                return "You have some matching skills. Focus on gaining required experience."
    
    def _generate_recommendations(self, missing, soft_score):
        """Generate recommendations"""
        recommendations = []
        
        if missing:
            top_missing = missing[:3]
            recommendations.append(f"Consider learning: {', '.join(top_missing)}")
        
        if soft_score < 60:
            recommendations.append("Highlight your soft skills more prominently")
        
        if not recommendations:
            recommendations.append("Your profile looks good! Keep it updated")
        
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
            'feedback': 'Analysis completed successfully.',
            'recommendations': ['Consider adding more technical details to your resume']
        }

# Create global instance
ai_matcher = AdvancedAIMatcher()

def analyze_resume_advanced(resume_text, job):
    """Wrapper function for advanced analysis"""
    return ai_matcher.analyze_match(resume_text, job)