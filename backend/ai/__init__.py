"""AI engine package: NL -> SQL translation, chart selection, insights and quality.

Modules
-------
provider        : LLM provider abstraction (OpenAI-compatible / local fallback)
columns         : column classification and dataset capability helpers
intent          : natural-language intent detection
sql_generator   : NL -> SQL generation (provider or local engine)
sql_validator   : intent/SQL consistency validation
chart_selector  : automatic chart type selection
insights        : executive summaries / recommendations / risks / follow-ups
quality         : AI quality scoring
"""
from .sql_generator import nl_to_sql, _local_nl_to_sql
from .sql_validator import validate_sql_intent
from .chart_selector import detect_chart_type
from .insights import generate_insights
from .quality import generate_ai_quality
from .provider import USE_AI, MODEL

__all__ = [
    "nl_to_sql",
    "_local_nl_to_sql",
    "validate_sql_intent",
    "detect_chart_type",
    "generate_insights",
    "generate_ai_quality",
    "USE_AI",
    "MODEL",
]
