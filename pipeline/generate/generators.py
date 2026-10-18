"""Parameterized deterministic question generators for Maths Maharathi.

Every generated question:
- Has an exact mathematical ground-truth answer.
- Is generated deterministically with a random seed.
- Is bilingual (English + Hindi).
- Includes plausible distractors based on common calculation errors.
- Sets source_type="original", rights_cleared=True.
- Is machine-verified before returning.
"""

from __future__ import annotations

import math
import random
import uuid
from typing import Any, Dict, List, Optional, Tuple

from pipeline.verify.solver import MathSolver
from schemas.enums import DifficultyLevel, ExamType, ReviewStatus, SourceType, TopicSlug
from schemas.models import Option, Question


class BaseTopicGenerator:
    """Base class for topic generators."""

    def __init__(self, rng: random.Random):
        self.rng = rng

    def make_options(
        self,
        correct_val: float,
        distractors: List[float],
        unit: str = "",
        is_int: bool = True,
    ) -> Tuple[List[Option], str]:
        """Creates 4 shuffled options and identifies the correct letter ('A', 'B', 'C', 'D')."""
        def fmt(v: float) -> str:
            if is_int or v.is_integer():
                s = str(int(round(v)))
            else:
                s = f"{v:.2f}"
            return f"{s} {unit}".strip()

        all_vals = [correct_val]
        for d in distractors:
            if d != correct_val and d not in all_vals:
                all_vals.append(d)
        
        # Ensure we have 4 unique values
        offset = 1.0
        while len(all_vals) < 4:
            cand = correct_val + offset
            if cand not in all_vals:
                all_vals.append(cand)
            offset += 1.0

        all_vals = all_vals[:4]
        self.rng.shuffle(all_vals)

        letters = ["A", "B", "C", "D"]
        options: List[Option] = []
        correct_opt = "A"

        for idx, val in enumerate(all_vals):
            letter = letters[idx]
            if val == correct_val:
                correct_opt = letter
            text = fmt(val)
            options.append(Option(id=letter, text_en=text, text_hi=text))

        return options, correct_opt


class SimplificationGenerator(BaseTopicGenerator):
    """Generates arithmetic & BODMAS simplification problems."""

    def generate(self, exam: ExamType, difficulty: DifficultyLevel) -> Question:
        if difficulty == DifficultyLevel.EASY:
            a = self.rng.randint(12, 45)
            b = self.rng.randint(4, 15)
            c = self.rng.randint(10, 50)
            # a * b + c
            exact = a * b + c
            text_en = f"What is the value of: {a} × {b} + {c}?"
            text_hi = f"मान ज्ञात कीजिए: {a} × {b} + {c}?"
            sol_en = f"Step 1: {a} × {b} = {a * b}\nStep 2: {a * b} + {c} = {exact}"
            sol_hi = f"चरण 1: {a} × {b} = {a * b}\nचरण 2: {a * b} + {c} = {exact}"
            distractors = [exact + b, exact - c, a * (b + c), exact + 10]
            target_secs = 20
        elif difficulty == DifficultyLevel.HARD:
            a = self.rng.randint(15, 30)
            sq = a * a
            b = self.rng.randint(12, 35)
            c = self.rng.randint(5, 20)
            d = self.rng.choice([2, 4, 5, 10])
            # sqrt(sq) + (b * c) / d
            mult = b * c
            exact = a + (mult / d)
            text_en = f"Evaluate: √{sq} + ({b} × {c}) ÷ {d}"
            text_hi = f"सरल करें: √{sq} + ({b} × {c}) ÷ {d}"
            sol_en = f"Step 1: √{sq} = {a}\nStep 2: ({b} × {c}) ÷ {d} = {mult} ÷ {d} = {mult / d}\nStep 3: {a} + {mult / d} = {exact}"
            sol_hi = f"चरण 1: √{sq} = {a}\nचरण 2: ({b} × {c}) ÷ {d} = {mult / d}\nचरण 3: {a} + {mult / d} = {exact}"
            distractors = [exact + 5, exact - 4, float(a * b), round(exact * 1.5, 2)]
            target_secs = 40
        else:
            # Medium: (A% of B) + C
            pct = self.rng.choice([15, 20, 25, 40, 50, 75])
            base = self.rng.choice([200, 300, 450, 500, 600, 800])
            c = self.rng.randint(25, 120)
            part = (pct * base) / 100
            exact = part + c
            text_en = f"Find the value of: {pct}% of {base} + {c}."
            text_hi = f"{base} का {pct}% + {c} का मान क्या होगा?"
            sol_en = f"Step 1: {pct}% of {base} = ({pct}/100) × {base} = {part}\nStep 2: {part} + {c} = {exact}"
            sol_hi = f"चरण 1: {base} का {pct}% = {part}\nचरण 2: {part} + {c} = {exact}"
            distractors = [part + c + 10, part - c if part > c else part + 20, exact + pct, exact - 15]
            target_secs = 30

        is_integer = float(exact).is_integer()
        options, correct_opt = self.make_options(float(exact), distractors, is_int=is_integer)

        q = Question(
            id=f"orig_simp_{uuid.uuid4().hex[:8]}",
            source_type=SourceType.ORIGINAL,
            rights_cleared=True,
            exam=exam,
            text_en=text_en,
            text_hi=text_hi,
            options=options,
            correct_option=correct_opt,
            solution_en=sol_en,
            solution_hi=sol_hi,
            topic_slug=TopicSlug.SIMPLIFICATION,
            difficulty=difficulty,
            target_seconds=target_secs,
            metadata={"generator_info": {"exact_answer": exact, "type": "arithmetic"}},
        )
        is_ok, details = MathSolver.verify_question(q)
        q.machine_verified = is_ok
        q.solver_output = details
        q.review_status = ReviewStatus.VERIFIED if is_ok else ReviewStatus.DRAFT
        return q


class ProfitLossGenerator(BaseTopicGenerator):
    """Generates profit, loss, cost price, and discount problems."""

    def generate(self, exam: ExamType, difficulty: DifficultyLevel) -> Question:
        cp = self.rng.choice([200, 350, 400, 500, 650, 800, 1200, 1500])
        profit_pct = self.rng.choice([10, 15, 20, 25, 30])
        sp = cp * (1 + profit_pct / 100.0)

        text_en = (
            f"An article is purchased for ₹{cp} and sold at a profit of {profit_pct}%. "
            f"What is the selling price of the article?"
        )
        text_hi = (
            f"एक वस्तु को ₹{cp} में खरीदा जाता है और {profit_pct}% के लाभ पर बेचा जाता है। "
            f"वस्तु का विक्रय मूल्य क्या है?"
        )
        sol_en = f"SP = CP × (1 + Profit%/100) = {cp} × (1 + {profit_pct}/100) = ₹{int(sp)}"
        sol_hi = f"विक्रय मूल्य = क्रय मूल्य × (1 + लाभ%/100) = {cp} × (1 + {profit_pct}/100) = ₹{int(sp)}"
        distractors = [sp + 50, sp - 50, cp * (1 - profit_pct / 100.0), sp + 100]

        options, correct_opt = self.make_options(float(sp), distractors, unit="₹", is_int=True)

        q = Question(
            id=f"orig_pl_{uuid.uuid4().hex[:8]}",
            source_type=SourceType.ORIGINAL,
            rights_cleared=True,
            exam=exam,
            text_en=text_en,
            text_hi=text_hi,
            options=options,
            correct_option=correct_opt,
            solution_en=sol_en,
            solution_hi=sol_hi,
            topic_slug=TopicSlug.PROFIT_LOSS,
            difficulty=difficulty,
            target_seconds=45,
            metadata={"generator_info": {"exact_answer": sp, "type": "profit_loss"}},
        )
        is_ok, details = MathSolver.verify_question(q)
        q.machine_verified = is_ok
        q.solver_output = details
        q.review_status = ReviewStatus.VERIFIED if is_ok else ReviewStatus.DRAFT
        return q


class InterestGenerator(BaseTopicGenerator):
    """Generates simple interest and compound interest problems."""

    def generate(self, exam: ExamType, difficulty: DifficultyLevel) -> Question:
        p = self.rng.choice([2000, 4000, 5000, 8000, 10000, 12000])
        r = self.rng.choice([5, 6, 8, 10, 12])
        t = self.rng.choice([2, 3, 4])
        si = (p * r * t) / 100.0

        text_en = (
            f"Find the Simple Interest on a principal amount of ₹{p} at an annual interest rate "
            f"of {r}% for a period of {t} years."
        )
        text_hi = (
            f"₹{p} के मूलधन पर {r}% वार्षिक ब्याज दर से {t} वर्षों का साधारण ब्याज कितना होगा?"
        )
        sol_en = f"SI = (P × R × T) / 100 = ({p} × {r} × {t}) / 100 = ₹{int(si)}"
        sol_hi = f"साधारण ब्याज = (मूलधन × दर × समय) / 100 = ({p} × {r} × {t}) / 100 = ₹{int(si)}"
        distractors = [si + 200, si - 200, (p * r) / 100.0, si + (p * 0.05)]

        options, correct_opt = self.make_options(float(si), distractors, unit="₹", is_int=True)

        q = Question(
            id=f"orig_si_{uuid.uuid4().hex[:8]}",
            source_type=SourceType.ORIGINAL,
            rights_cleared=True,
            exam=exam,
            text_en=text_en,
            text_hi=text_hi,
            options=options,
            correct_option=correct_opt,
            solution_en=sol_en,
            solution_hi=sol_hi,
            topic_slug=TopicSlug.SIMPLE_COMPOUND_INTEREST,
            difficulty=difficulty,
            target_seconds=45,
            metadata={"generator_info": {"exact_answer": si, "type": "simple_interest"}},
        )
        is_ok, details = MathSolver.verify_question(q)
        q.machine_verified = is_ok
        q.solver_output = details
        q.review_status = ReviewStatus.VERIFIED if is_ok else ReviewStatus.DRAFT
        return q


class TimeWorkGenerator(BaseTopicGenerator):
    """Generates combined work & efficiency problems."""

    def generate(self, exam: ExamType, difficulty: DifficultyLevel) -> Question:
        # Pick numbers that yield clean combined days
        pairs = [(10, 15, 6), (12, 24, 8), (20, 30, 12), (15, 30, 10), (12, 60, 10)]
        d_a, d_b, combined = self.rng.choice(pairs)

        text_en = (
            f"A can complete a piece of work in {d_a} days and B can complete the same work in {d_b} days. "
            f"If both work together, in how many days will the work be completed?"
        )
        text_hi = (
            f"A किसी कार्य को {d_a} दिनों में पूरा कर सकता है तथा B उसी कार्य को {d_b} दिनों में पूरा कर सकता है। "
            f"यदि दोनों एक साथ कार्य करें, तो कार्य कितने दिनों में पूरा होगा?"
        )
        sol_en = (
            f"A's 1-day work = 1/{d_a}\n"
            f"B's 1-day work = 1/{d_b}\n"
            f"Combined 1-day work = 1/{d_a} + 1/{d_b} = ({d_a + d_b})/({d_a * d_b}) = 1/{combined}\n"
            f"Total days = {combined} days"
        )
        sol_hi = f"A का 1 दिन का कार्य = 1/{d_a}, B का 1 दिन का कार्य = 1/{d_b}। कुल समय = {combined} दिन।"
        distractors = [float(combined + 2), float(combined - 2), float((d_a + d_b) / 2), float(combined + 4)]

        options, correct_opt = self.make_options(float(combined), distractors, unit="days", is_int=True)

        q = Question(
            id=f"orig_tw_{uuid.uuid4().hex[:8]}",
            source_type=SourceType.ORIGINAL,
            rights_cleared=True,
            exam=exam,
            text_en=text_en,
            text_hi=text_hi,
            options=options,
            correct_option=correct_opt,
            solution_en=sol_en,
            solution_hi=sol_hi,
            topic_slug=TopicSlug.TIME_WORK,
            difficulty=difficulty,
            target_seconds=50,
            metadata={"generator_info": {"exact_answer": combined, "type": "time_work"}},
        )
        is_ok, details = MathSolver.verify_question(q)
        q.machine_verified = is_ok
        q.solver_output = details
        q.review_status = ReviewStatus.VERIFIED if is_ok else ReviewStatus.DRAFT
        return q


class SpeedDistanceGenerator(BaseTopicGenerator):
    """Generates speed, time, distance and train problems."""

    def generate(self, exam: ExamType, difficulty: DifficultyLevel) -> Question:
        speed_kmh = self.rng.choice([36, 54, 72, 90, 108])  # Clean conversion to m/s (10, 15, 20, 25, 30)
        speed_ms = (speed_kmh * 5) / 18
        time_sec = self.rng.choice([12, 16, 20, 25, 30])
        train_len = speed_ms * time_sec

        text_en = (
            f"A train running at a speed of {speed_kmh} km/h crosses a standing pole in {time_sec} seconds. "
            f"What is the length of the train?"
        )
        text_hi = (
            f"{speed_kmh} किमी/घंटा की गति से चल रही एक ट्रेन एक खंभे को {time_sec} सेकंड में पार करती है। "
            f"ट्रेन की लंबाई ज्ञात कीजिए।"
        )
        sol_en = (
            f"Speed in m/s = {speed_kmh} × (5/18) = {int(speed_ms)} m/s\n"
            f"Length = Speed × Time = {int(speed_ms)} × {time_sec} = {int(train_len)} meters"
        )
        sol_hi = f"गति (मी/से) = {speed_kmh} × 5/18 = {int(speed_ms)} मी/से। लंबाई = {int(train_len)} मीटर।"
        distractors = [train_len + 50, train_len - 50, speed_kmh * time_sec, train_len + 100]

        options, correct_opt = self.make_options(float(train_len), distractors, unit="meters", is_int=True)

        q = Question(
            id=f"orig_spd_{uuid.uuid4().hex[:8]}",
            source_type=SourceType.ORIGINAL,
            rights_cleared=True,
            exam=exam,
            text_en=text_en,
            text_hi=text_hi,
            options=options,
            correct_option=correct_opt,
            solution_en=sol_en,
            solution_hi=sol_hi,
            topic_slug=TopicSlug.SPEED_TIME_DISTANCE,
            difficulty=difficulty,
            target_seconds=50,
            metadata={"generator_info": {"exact_answer": train_len, "type": "speed_distance"}},
        )
        is_ok, details = MathSolver.verify_question(q)
        q.machine_verified = is_ok
        q.solver_output = details
        q.review_status = ReviewStatus.VERIFIED if is_ok else ReviewStatus.DRAFT
        return q


class RatioProportionGenerator(BaseTopicGenerator):
    """Generates ratio division and proportional share problems."""

    def generate(self, exam: ExamType, difficulty: DifficultyLevel) -> Question:
        r_a = self.rng.randint(2, 5)
        r_b = self.rng.randint(3, 7)
        if r_a == r_b:
            r_b += 1
        unit_val = self.rng.choice([50, 100, 150, 200, 250])
        total_sum = (r_a + r_b) * unit_val
        share_a = r_a * unit_val

        text_en = (
            f"A sum of ₹{total_sum} is divided between A and B in the ratio {r_a} : {r_b}. "
            f"What is the share of A?"
        )
        text_hi = (
            f"₹{total_sum} की राशि को A और B के बीच {r_a} : {r_b} के अनुपात में विभाजित किया जाता है। "
            f"A का हिस्सा क्या होगा?"
        )
        sol_en = f"A's share = ({r_a}/({r_a} + {r_b})) × {total_sum} = ({r_a}/{r_a + r_b}) × {total_sum} = ₹{share_a}"
        sol_hi = f"A का हिस्सा = ({r_a}/{r_a + r_b}) × {total_sum} = ₹{share_a}"
        distractors = [share_a + unit_val, share_a - unit_val, r_b * unit_val, total_sum - share_a + 50]

        options, correct_opt = self.make_options(float(share_a), distractors, unit="₹", is_int=True)

        q = Question(
            id=f"orig_ratio_{uuid.uuid4().hex[:8]}",
            source_type=SourceType.ORIGINAL,
            rights_cleared=True,
            exam=exam,
            text_en=text_en,
            text_hi=text_hi,
            options=options,
            correct_option=correct_opt,
            solution_en=sol_en,
            solution_hi=sol_hi,
            topic_slug=TopicSlug.RATIO_PROPORTION,
            difficulty=difficulty,
            target_seconds=40,
            metadata={"generator_info": {"exact_answer": share_a, "type": "ratio"}},
        )
        is_ok, details = MathSolver.verify_question(q)
        q.machine_verified = is_ok
        q.solver_output = details
        q.review_status = ReviewStatus.VERIFIED if is_ok else ReviewStatus.DRAFT
        return q


class QuadraticEquationGenerator(BaseTopicGenerator):
    """Generates algebraic quadratic root problems."""

    def generate(self, exam: ExamType, difficulty: DifficultyLevel) -> Question:
        r1 = self.rng.choice([2, 3, 4, 5, 6])
        r2 = self.rng.choice([1, 2, 7, 8])
        # Equation: x^2 - (r1+r2)x + r1*r2 = 0
        b = -(r1 + r2)
        c = r1 * r2
        sign_b = f"- {abs(b)}" if b < 0 else f"+ {b}"
        sign_c = f"+ {c}" if c > 0 else f"- {abs(c)}"

        larger_root = max(r1, r2)
        text_en = f"Find the larger root of the quadratic equation: x² {sign_b}x {sign_c} = 0."
        text_hi = f"द्विघात समीकरण x² {sign_b}x {sign_c} = 0 का बड़ा मूल ज्ञात कीजिए।"
        sol_en = f"Roots are {r1} and {r2}. The larger root is {larger_root}."
        sol_hi = f"समीकरण के मूल {r1} और {r2} हैं। बड़ा मूल {larger_root} है।"
        distractors = [float(min(r1, r2)), float(-larger_root), float(larger_root + 1), float(r1 + r2)]

        options, correct_opt = self.make_options(float(larger_root), distractors, is_int=True)

        q = Question(
            id=f"orig_quad_{uuid.uuid4().hex[:8]}",
            source_type=SourceType.ORIGINAL,
            rights_cleared=True,
            exam=exam,
            text_en=text_en,
            text_hi=text_hi,
            options=options,
            correct_option=correct_opt,
            solution_en=sol_en,
            solution_hi=sol_hi,
            topic_slug=TopicSlug.QUADRATIC_EQUATIONS,
            difficulty=difficulty,
            target_seconds=35,
            metadata={"generator_info": {"exact_answer": larger_root, "type": "quadratic"}},
        )
        is_ok, details = MathSolver.verify_question(q)
        q.machine_verified = is_ok
        q.solver_output = details
        q.review_status = ReviewStatus.VERIFIED if is_ok else ReviewStatus.DRAFT
        return q


# Map topic slugs to their generator implementations
GENERATOR_REGISTRY = {
    TopicSlug.SIMPLIFICATION: SimplificationGenerator,
    TopicSlug.NUMBER_SERIES: SimplificationGenerator,
    TopicSlug.PERCENTAGE: SimplificationGenerator,
    TopicSlug.PROFIT_LOSS: ProfitLossGenerator,
    TopicSlug.SIMPLE_COMPOUND_INTEREST: InterestGenerator,
    TopicSlug.TIME_WORK: TimeWorkGenerator,
    TopicSlug.SPEED_TIME_DISTANCE: SpeedDistanceGenerator,
    TopicSlug.RATIO_PROPORTION: RatioProportionGenerator,
    TopicSlug.AVERAGES: RatioProportionGenerator,
    TopicSlug.QUADRATIC_EQUATIONS: QuadraticEquationGenerator,
    TopicSlug.ALGEBRA: QuadraticEquationGenerator,
}
