"""US small-cap quantitative screening engine.

Implements a five-condition screen over SEC filing data:

1. market capitalisation between $0.5bn and $3bn   (Fama-French size)
2. gross margin above 40% and improving            (Novy-Marx)
3. ROIC above WACC with a high reinvestment rate   (Mauboussin)
4. interest-bearing debt / EBITDA at or below 3x
5. insider ownership at or above 10%               (Jensen-Meckling)
"""

__version__ = "1.0.0"

from .config import Config
from .models import CriterionResult, ScreenResult, Verdict

__all__ = ["Config", "CriterionResult", "ScreenResult", "Verdict", "__version__"]
