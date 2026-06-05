import re
import logging
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Setup logging instead of print
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ResumeMatcher:
    def __init__(self):
        logger.info("Initializing Resume Matcher with TF-IDF...")
        
        # Expanded skill dictionary with more keywords
        self.tech_skills = {
            'python': ['python', 'django', 'flask', 'fastapi', 'numpy', 'pandas', 'jupyter', 'scipy'],
            'javascript': ['javascript', 'react', 'angular', 'vue', 'node', 'express', 'typescript', 'js', 'es6'],
            'java': ['java', 'spring', 'hibernate', 'maven', 'gradle', 'j2ee', 'servlet'],
            'sql': ['sql', 'mysql', 'postgresql', 'sqlite', 'mongodb', 'database', 'rdbms', 'nosql'],
            'aws': ['aws', 'ec2', 's3', 'lambda', 'cloud', 'amazon web services', 'route53', 'cloudfront'],
            'docker': ['docker', 'kubernetes', 'container', 'k8s', 'podman', 'dockerfile'],
            'git': ['git', 'github', 'gitlab', 'bitbucket', 'version control', 'vcs'],
            'html': ['html', 'css', 'bootstrap', 'tailwind', 'frontend', 'scss', 'sass'],
            'rest': ['rest', 'api', 'endpoint', 'restful', 'microservice', 'graphql'],
            'c++': ['c++', 'cpp', 'embedded', 'c plus plus'],
            'csharp': ['c#', '.net', 'asp.net', 'csharp', 'dotnet'],
            'php': ['php', 'laravel', 'wordpress', 'symfony'],
            'ruby': ['ruby', 'rails', 'ruby on rails'],
            'go': ['golang', 'go language', 'goland'],
            'rust': ['rust', 'cargo', 'rustlang'],
            'react': ['react', 'reactjs', 'react.js', 'next.js', 'nextjs'],
            'vue': ['vue', 'vuejs', 'vue.js', 'nuxt'],
            'angular': ['angular', 'angularjs', 'angular.js', 'ng'],
        }
        
        self.soft_skills = {
            'communication': ['communication', 'verbal', 'written', 'presentation', 'public speaking'],
            'leadership': ['leadership', 'lead', 'manage', 'mentor', 'supervise', 'team lead'],
            'teamwork': ['team', 'collaboration', 'cooperative', 'cross-functional', 'partnership'],
            'problemsolving': ['problem solving', 'analytical', 'troubleshoot', 'debug', 'critical thinking'],
            'timemanagement': ['time management', 'deadline', 'organized', 'planning', 'prioritization'],
        }
        
        self.edu_variations = {
            'phd': ['phd', 'doctorate', 'doctor of philosophy', 'd.phil'],
            'master': ['master', 'masters', 'ms', 'm.sc', 'm.tech', 'm.s', 'mtech', 'mca'],
            'bachelor': ['bachelor', 'bs', 'b.sc', 'ba', 'b.tech', 'b.e', 'be', 'b.s', 'btech', 'bca'],
            'associate': ['associate', 'diploma', 'polytechnic'],
            'highschool': ['high school', 'hsc', 'ssc', 'ged', 'secondary'],
        }
        
        # Education level values (for scoring)
        self.edu_level_values = {
            'phd': 5,
            'master': 4,
            'bachelor': 3,
            'associate': 2,
            'highschool': 1
        }
        
        self.certifications = {
            'aws': ['aws certified', 'amazon web services certified', 'aws solution architect'],
            'azure': ['azure certified', 'microsoft azure', 'az-', 'dp-'],
            'gcp': ['google cloud', 'gcp certified', 'google cloud platform'],
            'kubernetes': ['cka', 'ckad', 'kubernetes certification', 'cks'],
            'scrum': ['scrum master', 'psm', 'csm', 'agile certified', 'scrum.org'],
            'pmp': ['pmp', 'project management professional', 'pmi'],
            'security': ['cissp', 'security+', 'cybersecurity', 'ceh', 'oscp'],
            'python': ['pcp', 'python certified', 'pcep'],
            'java': ['ocjp', 'java certified', 'scjp'],
        }
        
        self.tfidf_vectorizer = TfidfVectorizer(max_features=500, stop_words='english')
        
        logger.info("Resume Matcher Ready!")
    
    def _tokenize_words(self, text):
        """Better tokenization that handles punctuation and slashes"""
        text_lower = text.lower()
        words = re.findall(r'\b[a-z0-9#+.]+\b', text_lower)
        return set(words)
    
    def extract_education(self, text):
        """Extract education degrees using pattern matching"""
        text_lower = text.lower()
        found_degrees = []
        
        # Check against education variations
        for degree_type, variations in self.edu_variations.items():
            for variation in variations:
                # Use word boundary to avoid partial matches
                if re.search(r'\b' + re.escape(variation) + r'\b', text_lower):
                    found_degrees.append(degree_type)
                    break
        
        # Look for degree with field (e.g., "Bachelor of Science in Computer Science")
        degree_patterns = [
            r'bachelor[^\w]*of[^\w]*(\w+(?:\s+\w+){0,2})',
            r'master[^\w]*of[^\w]*(\w+(?:\s+\w+){0,2})',
            r'b\.(\w+)',
            r'm\.(\w+)',
            r'be\s+in\s+(\w+)',
            r'btech\s+in\s+(\w+)',
        ]
        
        for pattern in degree_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                if match not in found_degrees:
                    found_degrees.append(match)
        
        # Remove duplicates and return
        result = list(set(found_degrees)) if found_degrees else []
        
        if not result:
            logger.debug("No education found in text")
        
        return result
    
    def extract_certifications(self, text):
        """Extract professional certifications"""
        text_lower = text.lower()
        found = []
        
        for cert, keywords in self.certifications.items():
            for keyword in keywords:
                if keyword in text_lower:
                    found.append(cert.upper())
                    break
        
        if found:
            logger.debug(f"Found certifications: {found}")
        
        return found
    
    def extract_experience(self, text):
        """Extract years of experience using comprehensive patterns"""
        text_lower = text.lower()
        
        # Comprehensive experience patterns
        patterns = [
            # Pattern, multiplier, description
            (r'(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)(?:\s+of)?\s+experience', 1),
            (r'experience of (\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)', 1),
            (r'(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+(?:of|in|as)', 1),
            (r'minimum\s+(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)', 1),  # "minimum 3 years"
            (r'at\s+least\s+(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)', 1),  # "at least 2 years"
            (r'(\d+(?:\.\d+)?)\+?\s*\+?\s*(?:years?|yrs?)\s+experience', 1),
            (r'(\d+(?:\.\d+)?)\+?\s*months?', 0.08333),  # months to years
            (r'(\d+(?:\.\d+)?)\+?\s*months?\s+experience', 0.08333),
        ]
        
        max_years = 0
        for pattern, multiplier in patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                try:
                    years = float(match) * multiplier
                    max_years = max(max_years, years)
                except (ValueError, TypeError):
                    pass
        
        # Handle written numbers
        number_words = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15
        }
        
        for word, num in number_words.items():
            if re.search(rf'\b{word}\s+(?:years?|yrs?)', text_lower):
                max_years = max(max_years, num)
        
        # Handle ranges (e.g., "3-5 years" -> take the lower bound)
        range_pattern = r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)'
        matches = re.findall(range_pattern, text_lower)
        for match in matches:
            try:
                # Take the lower bound as minimum experience
                max_years = max(max_years, float(match[0]))
            except (ValueError, TypeError):
                pass
        
        if max_years > 0:
            logger.debug(f"Extracted experience: {max_years} years")
        else:
            logger.debug("No experience found in text")
        
        return max_years
    
    def extract_technical_skills(self, text):
        """Extract technical skills using exact keyword matching"""
        text_lower = text.lower()
        found = {}
        
        for skill, keywords in self.tech_skills.items():
            skill_score = 0
            for keyword in keywords:
                # Use word boundary to avoid partial matches
                if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                    skill_score += 1
            if skill_score > 0:
                # Normalize to 0-100 based on how many keywords matched
                found[skill] = min(100, (skill_score / len(keywords)) * 100)
        
        if found:
            logger.debug(f"Found technical skills: {list(found.keys())[:5]}")
        
        return found
    
    def extract_soft_skills(self, text):
        """Extract soft skills using exact keyword matching"""
        text_lower = text.lower()
        found = []
        
        for skill, keywords in self.soft_skills.items():
            for keyword in keywords:
                if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                    found.append(skill)
                    break
        
        if found:
            logger.debug(f"Found soft skills: {found}")
        
        return list(set(found))
    
    def calculate_semantic_similarity(self, resume_text, job_text):
        """Calculate TF-IDF similarity between two texts"""
        try:
            # Create a fresh vectorizer for each call (thread-safe)
            vectorizer = TfidfVectorizer(max_features=500, stop_words='english')
            corpus = [resume_text, job_text]
            tfidf_matrix = vectorizer.fit_transform(corpus)
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            logger.debug(f"Semantic similarity: {similarity}")
            return similarity
        except Exception as e:
            logger.error(f"TF-IDF similarity failed: {e}")
            # Fallback to simple token overlap
            resume_words = self._tokenize_words(resume_text)
            job_words = self._tokenize_words(job_text)
            if not job_words:
                return 0.5
            overlap = len(resume_words.intersection(job_words))
            similarity = min(1.0, overlap / len(job_words))
            logger.debug(f"Fallback similarity: {similarity}")
            return similarity
    
    def calculate_education_score(self, resume_education_list, job_text):
        """Calculate education level match score - FIXED: now accepts list and job text"""
        job_lower = job_text.lower()
        
        # Find highest required education level in job
        required_level = 0
        required_degree = None
        
        for edu_type, variations in self.edu_variations.items():
            for variation in variations:
                if re.search(r'\b' + re.escape(variation) + r'\b', job_lower):
                    # Get level value
                    if edu_type in self.edu_level_values:
                        if self.edu_level_values[edu_type] > required_level:
                            required_level = self.edu_level_values[edu_type]
                            required_degree = edu_type
        
        # Find highest resume education level
        resume_level = 0
        
        # Convert the education list to a string for easier matching
        resume_edu_str = ' '.join(resume_education_list).lower() if resume_education_list else ''
        
        for edu_type, level in self.edu_level_values.items():
            # Check if this education type appears in resume
            if edu_type in resume_edu_str:
                resume_level = max(resume_level, level)
            else:
                # Check variations
                for variation in self.edu_variations.get(edu_type, []):
                    if variation in resume_edu_str:
                        resume_level = max(resume_level, level)
                        break
        
        # If no requirement found, score is 1.0 (no penalty)
        if required_level == 0:
            logger.debug("No education requirement found, score = 1.0")
            return 1.0
        
        # Calculate score
        if resume_level >= required_level:
            score = 1.0
        elif resume_level == 0:
            score = 0.0
        else:
            score = resume_level / required_level
        
        # Ensure score is between 0 and 1
        score = max(0.0, min(1.0, score))
        
        logger.debug(f"Education score: {score} (required: {required_level}, resume: {resume_level})")
        return score
    
    def calculate_experience_score(self, resume_years, job_text):
        """Calculate experience match score"""
        job_lower = job_text.lower()
        
        # Extract required years from job with comprehensive patterns
        required_years = 0
        
        patterns = [
            r'(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+of\s+experience',
            r'(\d+(?:\.\d+)?)\+?\s*\+\s*(?:years?|yrs?)',
            r'minimum\s+(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)',
            r'at\s+least\s+(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)',
            r'(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+required',
            r'requires?\s+(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, job_lower)
            for match in matches:
                try:
                    required_years = max(required_years, float(match))
                except (ValueError, TypeError):
                    pass
        
        # If no requirement found, score is 1.0 (no penalty)
        if required_years == 0:
            logger.debug("No experience requirement found, score = 1.0")
            return 1.0
        
        # Calculate score
        if resume_years >= required_years:
            score = 1.0
        elif resume_years == 0:
            score = 0.0
        elif resume_years >= required_years * 0.8:
            score = 0.9
        elif resume_years >= required_years * 0.6:
            score = 0.75
        elif resume_years >= required_years * 0.4:
            score = 0.5
        else:
            score = max(0.2, resume_years / required_years)
        
        logger.debug(f"Experience score: {score} (required: {required_years}, resume: {resume_years})")
        return score
    
    def calculate_certification_score(self, resume_certs, job_text):
        """Calculate certification match score"""
        job_lower = job_text.lower()
        required_certs = []
        
        for cert, keywords in self.certifications.items():
            for keyword in keywords:
                if keyword in job_lower:
                    required_certs.append(cert)
                    break
        
        # If no certification required, score is 1.0 (no penalty)
        if not required_certs:
            logger.debug("No certification requirements found, score = 1.0")
            return 1.0
        
        # Calculate score
        matched = sum(1 for cert in required_certs if cert in resume_certs)
        score = matched / len(required_certs)
        
        logger.debug(f"Certification score: {score} (required: {required_certs}, resume: {resume_certs})")
        return score
    
    def _calculate_tech_score(self, resume_tech, required_tech):
        """Calculate technical skills match score"""
        # If no skills required, return 1.0 (no penalty)
        if not required_tech:
            logger.debug("No technical skills required, score = 1.0")
            return 1.0
        
        total_score = 0.0
        max_possible = 0.0
        
        for skill, required_weight in required_tech.items():
            max_possible += required_weight
            if skill in resume_tech:
                resume_weight = resume_tech[skill]
                # Take the minimum of required and resume weights (can't exceed what's needed)
                total_score += min(required_weight, resume_weight)
        
        score = total_score / max_possible if max_possible > 0 else 1.0
        logger.debug(f"Technical score: {score:.2f}")
        return score
    
    def _calculate_soft_score(self, resume_soft, required_soft):
        """Calculate soft skills match score"""
        # If no soft skills required, return 1.0 (no penalty)
        if not required_soft:
            logger.debug("No soft skills required, score = 1.0")
            return 1.0
        
        # Calculate score based on required skills
        matched = sum(1 for skill in required_soft if skill in resume_soft)
        score = matched / len(required_soft) if required_soft else 1.0
        
        logger.debug(f"Soft skills score: {score:.2f} ({matched}/{len(required_soft)})")
        return score
    
    def _extract_required_years(self, text):
        """Helper to extract required years from job text"""
        patterns = [
            r'(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+of\s+experience',
            r'minimum\s+(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)',
            r'at\s+least\s+(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text.lower())
            for match in matches:
                try:
                    return float(match)
                except:
                    pass
        return 0
    
    def match(self, resume_text, job_description, job_title=""):
        """
        Main matching function - returns scores and details
        This function is thread-safe and handles errors properly
        """
        try:
            # Input validation
            if not resume_text or not isinstance(resume_text, str):
                logger.error("Invalid resume text provided")
                return self._error_response("No resume text provided")
            
            if not job_description or not isinstance(job_description, str):
                logger.error("Invalid job description provided")
                return self._error_response("No job description provided")
            
            logger.info(f"Starting match analysis for job: {job_title[:50] if job_title else 'Unknown'}")
            
            # Extract features
            resume_education = self.extract_education(resume_text)
            resume_certs = self.extract_certifications(resume_text)
            resume_years = self.extract_experience(resume_text)
            resume_tech = self.extract_technical_skills(resume_text)
            resume_soft = self.extract_soft_skills(resume_text)
            
            # Job text for requirement extraction
            job_full = f"{job_title} {job_description}"
            required_tech = self.extract_technical_skills(job_full)
            required_soft = self.extract_soft_skills(job_full)
            
            # Calculate scores (returns 0-1, then convert to 0-100)
            tech_score_raw = self._calculate_tech_score(resume_tech, required_tech)
            soft_score_raw = self._calculate_soft_score(resume_soft, required_soft)
            exp_score_raw = self.calculate_experience_score(resume_years, job_full)
            edu_score_raw = self.calculate_education_score(resume_education, job_full)
            cert_score_raw = self.calculate_certification_score(resume_certs, job_full)
            semantic_score_raw = self.calculate_semantic_similarity(resume_text, job_full)
            
            # Convert to 0-100 scale
            tech_score = tech_score_raw * 100
            soft_score = soft_score_raw * 100
            exp_score = exp_score_raw * 100
            edu_score = edu_score_raw * 100
            cert_score = cert_score_raw * 100
            semantic_score = semantic_score_raw * 100
            
            # Ensure scores are valid (0-100)
            tech_score = max(0.0, min(100.0, tech_score))
            soft_score = max(0.0, min(100.0, soft_score))
            exp_score = max(0.0, min(100.0, exp_score))
            edu_score = max(0.0, min(100.0, edu_score))
            cert_score = max(0.0, min(100.0, cert_score))
            semantic_score = max(0.0, min(100.0, semantic_score))
            
            # Overall weighted score (weights sum to 1.0)
            overall = (
                (tech_score_raw * 0.45) +
                (soft_score_raw * 0.15) +
                (exp_score_raw * 0.20) +
                (edu_score_raw * 0.10) +
                (cert_score_raw * 0.05) +
                (semantic_score_raw * 0.05)
            ) * 100
            
            # Generate feedback and recommendations
            feedback, recommendations = self._generate_detailed_feedback(
                overall, tech_score, soft_score, exp_score, edu_score, cert_score,
                resume_tech, required_tech, resume_soft, required_soft,
                resume_years, job_full
            )
            
            result = {
                'overall_score': round(overall, 1),
                'technical_score': round(tech_score, 1),
                'soft_skills_score': round(soft_score, 1),
                'experience_score': round(exp_score, 1),
                'education_score': round(edu_score, 1),
                'certification_score': round(cert_score, 1),
                'semantic_score': round(semantic_score, 1),
                'matched_skills': list(resume_tech.keys())[:10],
                'missing_skills': [s for s in required_tech.keys() if s not in resume_tech][:10],
                'matched_soft': resume_soft[:5],
                'missing_soft': [s for s in required_soft if s not in resume_soft][:5],
                'years_experience': resume_years,
                'education_found': resume_education[:3],
                'certifications_found': resume_certs[:3],
                'feedback': feedback,
                'recommendations': recommendations
            }
            
            logger.info(f"Match completed. Overall score: {overall:.1f}")
            return result
            
        except Exception as e:
            logger.error(f"Matching failed with error: {str(e)}", exc_info=True)
            return self._error_response(f"Matching failed: {str(e)}")
    
    def _generate_detailed_feedback(self, overall, tech_score, soft_score, exp_score, edu_score, cert_score,
                                     resume_tech, required_tech, resume_soft, required_soft,
                                     resume_years, job_text):
        """Generate detailed feedback and recommendations"""
        
        # Main feedback based on overall score
        if overall >= 85:
            feedback = "Excellent match! Your profile aligns very well with this position."
        elif overall >= 75:
            feedback = "Good match. You have most of the key qualifications."
        elif overall >= 65:
            feedback = "Moderate match. Consider highlighting relevant skills more prominently."
        elif overall >= 50:
            feedback = "Below average match. Review missing skills and update your resume."
        else:
            feedback = "Low match. Your resume needs significant updates for this role."
        
        recommendations = []
        
        # Technical skill recommendations
        missing_tech = [s for s in required_tech if s not in resume_tech]
        if missing_tech and tech_score < 60:
            top_missing = missing_tech[:3]
            recommendations.append(f"💻 Add experience with: {', '.join(top_missing)}")
        
        # Soft skill recommendations
        missing_soft = [s for s in required_soft if s not in resume_soft]
        if missing_soft and soft_score < 60:
            recommendations.append(f"🗣️ Highlight soft skills: {', '.join(missing_soft[:2])}")
        
        # Experience recommendations
        req_years = self._extract_required_years(job_text)
        if req_years > 0 and resume_years < req_years and exp_score < 60:
            gap = req_years - resume_years
            if gap > 0:
                recommendations.append(f"⏰ Gain {round(gap, 1)} more years of experience to meet requirement")
        
        # Education recommendations
        if edu_score < 50:
            recommendations.append("🎓 Consider pursuing relevant education or certifications")
        
        # Certification recommendations
        if cert_score < 50:
            recommendations.append("📜 Consider obtaining relevant certifications")
        
        # Positive feedback if doing well
        if not recommendations and overall >= 75:
            recommendations.append("✅ Your profile looks strong! Keep it updated.")
        elif not recommendations:
            recommendations.append("📝 Add more specific technical details and achievements to your resume")
        
        return feedback, recommendations
    
    def _error_response(self, error_message):
        """Return a proper error response instead of fake scores"""
        return {
            'overall_score': None,
            'technical_score': None,
            'soft_skills_score': None,
            'experience_score': None,
            'education_score': None,
            'certification_score': None,
            'semantic_score': None,
            'matched_skills': [],
            'missing_skills': [],
            'matched_soft': [],
            'missing_soft': [],
            'years_experience': None,
            'education_found': [],
            'certifications_found': [],
            'feedback': f"Error: {error_message}",
            'recommendations': ["Check that both resume and job description are provided", 
                               "Ensure text is readable", 
                               "Try again or contact support"],
            'error': True
        }


def analyze_resume(resume_text, job_description, job_title=""):
    """Main function - creates new instance per call (thread-safe)"""
    matcher = ResumeMatcher()
    return matcher.match(resume_text, job_description, job_title)