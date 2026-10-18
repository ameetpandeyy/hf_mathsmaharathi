"""Topic classification, difficulty assignment, and solving time estimation.

Uses a high-performance rules-first engine with optional Gemini API LLM fallback.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional, Tuple

from schemas.enums import DifficultyLevel, TopicSlug
from schemas.models import Question

logger = logging.getLogger(__name__)

# Topic keyword and regex rules (English + Hindi)
TOPIC_RULES: Dict[TopicSlug, List[str]] = {
    TopicSlug.SIMPLIFICATION: [
        r"simplify", r"value of", r"evaluation", r"bodmas", r"square root", r"cube root",
        r"सरल करें", r"मान क्या है", r"वर्गमूल", r"घनमूल", r"[\d\s\+\-\*\/\(\)\^\=\.×÷]{8,}"
    ],
    TopicSlug.PERCENTAGE: [
        r"percent", r"\%", r"percentage", r"प्रतिशत", r"प्रतिशती"
    ],
    TopicSlug.PROFIT_LOSS: [
        r"cost price", r"selling price", r"marked price", r"profit", r"loss", r"discount",
        r"cr\b", r"sp\b", r"cp\b", r"mp\b", r"क्रय मूल्य", r"विक्रय मूल्य", r"अंकित मूल्य", r"लाभ", r"हानि", r"छूट"
    ],
    TopicSlug.SIMPLE_COMPOUND_INTEREST: [
        r"simple interest", r"compound interest", r"sum of money", r"compounded annually",
        r"rate of interest", r"per annum", r"साधारण ब्याज", r"चक्रवृद्धि ब्याज", r"ब्याज दर"
    ],
    TopicSlug.RATIO_PROPORTION: [
        r"ratio", r"proportion", r"proportional", r"\b\d+:\d+\b", r"अनुपात", r"समानुपात"
    ],
    TopicSlug.TIME_WORK: [
        r"can complete a work", r"days to finish", r"pipe", r"cistern", r"efficiency",
        r"कार्य", r"दिन में पूरा", r"नल", r"टंकी", r"क्षमता"
    ],
    TopicSlug.SPEED_TIME_DISTANCE: [
        r"speed", r"distance", r"km\/h", r"kmph", r"m\/s", r"train", r"stream", r"boat",
        r"upstream", r"downstream", r"गति", r"दूरी", r"ट्रेन", r"नाव", r"धारा"
    ],
    TopicSlug.AVERAGES: [
        r"average", r"mean weight", r"average age", r"औसत", r"माध्य"
    ],
    TopicSlug.MIXTURES_ALLIGATION: [
        r"mixture", r"alligation", r"milk and water", r"replaced by", r"मिश्रण", r"मिश्रित"
    ],
    TopicSlug.QUADRATIC_EQUATIONS: [
        r"roots of the equation", r"x\^2", r"quadratic", r"मूल", r"द्विघात समीकरण"
    ],
    TopicSlug.ALGEBRA: [
        r"algebra", r"polynomial", r"identity", r"a\^3\s*\+\s*b\^3", r"x\s*\+\s*1\/x",
        r"बीजगणित", r"सर्वसमिका"
    ],
    TopicSlug.GEOMETRY: [
        r"triangle", r"circle", r"tangent", r"chord", r"radius", r"diameter", r"angle",
        r"hypotenuse", r"त्रिभुज", r"वृत्त", r"त्रिज्या", r"व्यास", r"कोण"
    ],
    TopicSlug.MENSURATION: [
        r"cylinder", r"cone", r"sphere", r"cuboid", r"cube", r"hemisphere", r"curved surface area",
        r"volume", r"perimeter", r"बेलन", r"शंकु", r"गोला", r"आयतन", r"पृष्ठीय क्षेत्रफल", r"परिमाप"
    ],
    TopicSlug.TRIGONOMETRY: [
        r"\bsin\b", r"\bcos\b", r"\btan\b", r"\bsec\b", r"\bcosec\b", r"\bcot\b",
        r"height and distance", r"elevation", r"depression", r"त्रिकोणमिति"
    ],
    TopicSlug.NUMBER_SERIES: [
        r"missing term", r"next number in the series", r"wrong number in the series",
        r"संख्या श्रृंखला", r"अगली संख्या"
    ],
    TopicSlug.DATA_INTERPRETATION: [
        r"bar graph", r"pie chart", r"table shows", r"histogram", r"line graph",
        r"तालिका", r"पाई चार्ट", r"दंड आरेख"
    ],
}

# Standard time budgets per topic in seconds
TOPIC_TIME_BUDGETS: Dict[TopicSlug, int] = {
    TopicSlug.SIMPLIFICATION: 25,
    TopicSlug.NUMBER_SERIES: 30,
    TopicSlug.PERCENTAGE: 40,
    TopicSlug.RATIO_PROPORTION: 40,
    TopicSlug.PROFIT_LOSS: 45,
    TopicSlug.SIMPLE_COMPOUND_INTEREST: 50,
    TopicSlug.TIME_WORK: 50,
    TopicSlug.SPEED_TIME_DISTANCE: 50,
    TopicSlug.AVERAGES: 40,
    TopicSlug.MIXTURES_ALLIGATION: 45,
    TopicSlug.QUADRATIC_EQUATIONS: 35,
    TopicSlug.ALGEBRA: 45,
    TopicSlug.GEOMETRY: 55,
    TopicSlug.MENSURATION: 55,
    TopicSlug.TRIGONOMETRY: 50,
    TopicSlug.DATA_INTERPRETATION: 65,
}


class QuestionClassifier:
    """Classifies math questions, assigns difficulty, and estimates solving duration."""

    @classmethod
    def rule_based_classify(cls, text: str) -> Tuple[Optional[TopicSlug], float]:
        """Runs fast regex rule matching across known topics."""
        lower_text = text.lower()
        scored: List[Tuple[TopicSlug, int]] = []

        for topic, patterns in TOPIC_RULES.items():
            score = 0
            for pat in patterns:
                matches = len(re.findall(pat, lower_text, re.IGNORECASE))
                if matches > 0:
                    score += matches * 2
            if score > 0:
                scored.append((topic, score))

        if not scored:
            return None, 0.0

        scored.sort(key=lambda x: x[1], reverse=True)
        top_topic, top_score = scored[0]
        confidence = min(1.0, 0.4 + (top_score * 0.15))
        return top_topic, confidence

    @classmethod
    def llm_classify(cls, text: str) -> Optional[TopicSlug]:
        """Optional Gemini LLM fallback for ambiguous math statements."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None

        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = (
                f"Classify this competitive exam math question into exactly ONE of the following slugs:\n"
                f"{[t.value for t in TopicSlug]}\n\n"
                f"Question:\n{text}\n\n"
                f"Return ONLY the slug, nothing else."
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            raw = response.text.strip().lower()
            for slug in TopicSlug:
                if slug.value in raw:
                    return slug
        except Exception as exc:
            logger.warning("Gemini LLM classification fallback failed: %s", exc)

        return None

    @classmethod
    def estimate_difficulty(cls, text: str, topic: TopicSlug) -> DifficultyLevel:
        """Determines difficulty (EASY, MEDIUM, HARD) based on length, steps, and topic."""
        word_count = len(text.split())
        numbers_count = len(re.findall(r"\d+", text))

        # Hard criteria
        if topic in (TopicSlug.GEOMETRY, TopicSlug.MENSURATION, TopicSlug.SIMPLE_COMPOUND_INTEREST) and word_count > 45:
            return DifficultyLevel.HARD
        if numbers_count >= 6 or word_count > 60:
            return DifficultyLevel.HARD

        # Easy criteria
        if topic in (TopicSlug.SIMPLIFICATION, TopicSlug.NUMBER_SERIES) and word_count < 25:
            return DifficultyLevel.EASY
        if word_count < 20 and numbers_count <= 2:
            return DifficultyLevel.EASY

        return DifficultyLevel.MEDIUM

    @classmethod
    def classify_question(cls, question: Question) -> Question:
        """Enriches question with classified topic_slug, difficulty, and target_seconds."""
        combined_text = f"{question.text_en} {question.text_hi or ''}"
        
        # 1. Rules first
        topic, conf = cls.rule_based_classify(combined_text)

        # 2. LLM second if rules could not identify topic
        if not topic or conf < 0.5:
            llm_topic = cls.llm_classify(question.text_en)
            if llm_topic:
                topic = llm_topic

        # Fallback default
        if not topic:
            topic = TopicSlug.SIMPLIFICATION

        question.topic_slug = topic
        question.difficulty = cls.estimate_difficulty(question.text_en, topic)
        question.target_seconds = TOPIC_TIME_BUDGETS.get(topic, 45)
        return question
