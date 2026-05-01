"""Inheritance challenge: deep class hierarchies, MRO, method overrides.

Tests the agent's ability to follow class inheritance chains, identify which
file a method actually resolves to (through overrides), and understand
multiple inheritance / mixin patterns.
"""

from __future__ import annotations

from ..generator import (
    Difficulty,
    GroundTruthQuestion,
    ScoringMethod,
    SizeTier,
    SyntheticRepo,
    _pad_with_helpers,
)

_CHAIN_DEPTH = {SizeTier.XS: 3, SizeTier.S: 4, SizeTier.M: 5, SizeTier.L: 6, SizeTier.XL: 7}
_LINES = {SizeTier.XS: 20, SizeTier.S: 30, SizeTier.M: 50, SizeTier.L: 65, SizeTier.XL: 55}


def generate(size: SizeTier) -> SyntheticRepo:
    files: dict[str, str] = {}
    questions: list[GroundTruthQuestion] = []

    chain_depth = _CHAIN_DEPTH[size]
    target_lines = _LINES[size]

    # -- Linear inheritance chain: Base -> Layer1 -> Layer2 -> ... -> Concrete --
    class_names = ["BaseProcessor", "ValidatingProcessor", "LoggingProcessor",
                   "CachingProcessor", "MetricsProcessor", "TracingProcessor", "FinalProcessor"][:chain_depth]
    files_in_chain = []

    files["processors/__init__.py"] = ""

    for i, cls_name in enumerate(class_names):
        mod_name = cls_name.lower()
        mod_file = f"processors/{mod_name}.py"
        files_in_chain.append(mod_file)

        if i == 0:
            # Base class
            src = (
                f'"""Base processor -- root of the inheritance chain."""\n\n\n'
                f'class {cls_name}:\n'
                f'    """Abstract base processor."""\n\n'
                f'    def process(self, data: dict) -> dict:\n'
                f'        """Process data (base implementation)."""\n'
                f'        return {{"processed": True, "data": data}}\n\n'
                f'    def validate(self, data: dict) -> bool:\n'
                f'        """Validate input data."""\n'
                f'        return isinstance(data, dict) and len(data) > 0\n\n'
                f'    def get_name(self) -> str:\n'
                f'        """Return processor name."""\n'
                f'        return "{cls_name}"\n\n'
                f'    def cleanup(self):\n'
                f'        """Release resources."""\n'
                f'        pass\n'
            )
        else:
            parent = class_names[i - 1]
            parent_mod = parent.lower()
            # Override process() at each level, but leave validate() alone
            # until the 3rd level where it gets overridden
            override_validate = i == 2
            src_lines = [
                f'"""Processor layer {i}: {cls_name}."""\n',
                f'from .{parent_mod} import {parent}\n\n\n',
                f'class {cls_name}({parent}):\n',
                f'    """{cls_name} extends {parent}."""\n\n',
                f'    def process(self, data: dict) -> dict:\n',
                f'        """Process with {cls_name.lower()} logic then delegate."""\n',
                f'        data["{mod_name}_applied"] = True\n',
                f'        return super().process(data)\n',
            ]
            if override_validate:
                src_lines.extend([
                    f'\n    def validate(self, data: dict) -> bool:\n',
                    f'        """Strict validation at {cls_name} level."""\n',
                    f'        if "type" not in data:\n',
                    f'            return False\n',
                    f'        return super().validate(data)\n',
                ])
            src_lines.extend([
                f'\n    def get_name(self) -> str:\n',
                f'        return "{cls_name}"\n',
            ])
            src = "\n".join(src_lines)

        src = _pad_with_helpers(src, target_lines, f"proc{i}")
        files[mod_file] = src

    # Question: which file does process() resolve to at the end of the chain?
    questions.append(GroundTruthQuestion(
        id="inh_q1",
        question=f"If I call process() on a {class_names[-1]} instance, which file contains the first process() that runs?",
        workflow_type="CALL_GRAPH",
        expected={"file": files_in_chain[-1], "symbol": "process", "class": class_names[-1]},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.HARD,
    ))
    questions.append(GroundTruthQuestion(
        id="inh_q2",
        question=f"Where is the validate() method overridden in the {class_names[0]} hierarchy?",
        workflow_type="SYMBOL_LOOKUP",
        expected={
            "override_file": files_in_chain[2] if chain_depth > 2 else files_in_chain[0],
            "base_file": files_in_chain[0],
            "symbol": "validate",
        },
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.HARD,
    ))
    questions.append(GroundTruthQuestion(
        id="inh_q3",
        question=f"What is the class hierarchy / inheritance chain for {class_names[-1]}?",
        workflow_type="FEATURE_EXPLANATION",
        expected={
            "chain": class_names,
            "files": files_in_chain,
            "keywords": ["inherit", "extends", "super", "chain"],
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.MEDIUM,
    ))

    # -- Mixin pattern: multiple inheritance --
    files["mixins/__init__.py"] = ""
    files["mixins/serializable.py"] = (
        '"""Serialization mixin."""\n\n\n'
        'class SerializableMixin:\n'
        '    """Adds JSON serialization to any class."""\n\n'
        '    def to_dict(self) -> dict:\n'
        '        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}\n\n'
        '    def to_json(self) -> str:\n'
        '        import json\n'
        '        return json.dumps(self.to_dict())\n'
    )
    files["mixins/loggable.py"] = (
        '"""Logging mixin."""\n\n\n'
        'class LoggableMixin:\n'
        '    """Adds logging capabilities to any class."""\n\n'
        '    def log(self, message: str):\n'
        '        print(f"[{self.__class__.__name__}] {message}")\n\n'
        '    def log_error(self, error: str):\n'
        '        print(f"[{self.__class__.__name__} ERROR] {error}")\n'
    )
    files["mixins/cacheable.py"] = (
        '"""Caching mixin."""\n\n\n'
        'class CacheableMixin:\n'
        '    """Adds caching to any class."""\n\n'
        '    _cache: dict = {}\n\n'
        '    def cache_get(self, key: str):\n'
        '        return self._cache.get(key)\n\n'
        '    def cache_set(self, key: str, value):\n'
        '        self._cache[key] = value\n'
    )

    # Concrete class using multiple mixins
    base_cls = class_names[0]
    base_mod = base_cls.lower()
    files["composite.py"] = (
        '"""Composite class using multiple inheritance with mixins."""\n\n'
        f'from processors.{base_mod} import {base_cls}\n'
        'from mixins.serializable import SerializableMixin\n'
        'from mixins.loggable import LoggableMixin\n'
        'from mixins.cacheable import CacheableMixin\n\n\n'
        f'class CompositeProcessor({base_cls}, SerializableMixin, LoggableMixin, CacheableMixin):\n'
        '    """Processor with serialization, logging, and caching."""\n\n'
        '    def process(self, data: dict) -> dict:\n'
        '        self.log(f"Processing {len(data)} items")\n'
        '        cached = self.cache_get(str(data))\n'
        '        if cached:\n'
        '            return cached\n'
        '        result = super().process(data)\n'
        '        self.cache_set(str(data), result)\n'
        '        return result\n'
    )

    questions.append(GroundTruthQuestion(
        id="inh_q4",
        question="What is the MRO (method resolution order) for CompositeProcessor?",
        workflow_type="FEATURE_EXPLANATION",
        expected={
            "mro": ["CompositeProcessor", base_cls, "SerializableMixin", "LoggableMixin", "CacheableMixin"],
            "file": "composite.py",
            "keywords": ["mixin", "multiple inheritance", "MRO"],
        },
        scoring=ScoringMethod.CONTAINS_KEYWORDS,
        difficulty=Difficulty.HARD,
    ))
    questions.append(GroundTruthQuestion(
        id="inh_q5",
        question="If I call to_dict() on a CompositeProcessor, where is that method defined?",
        workflow_type="GOTO_DEFINITION_NO_FILE",
        expected={"file": "mixins/serializable.py", "symbol": "to_dict"},
        scoring=ScoringMethod.FILE_AND_SYMBOL_MATCH,
        difficulty=Difficulty.MEDIUM,
    ))

    # -- Filler for larger sizes --
    _extra = {SizeTier.XS: 0, SizeTier.S: 2, SizeTier.M: 15, SizeTier.L: 50, SizeTier.XL: 140}
    for i in range(_extra[size]):
        fname = f"extensions/ext_{i:03d}.py"
        if "extensions/__init__.py" not in files:
            files["extensions/__init__.py"] = ""
        src = (
            f'"""Extension module {i}."""\n\n'
            f'from processors.{base_mod} import {base_cls}\n\n\n'
            f'class Extension{i}({base_cls}):\n'
            f'    def process(self, data: dict) -> dict:\n'
            f'        data["ext_{i}"] = True\n'
            f'        return super().process(data)\n'
        )
        src = _pad_with_helpers(src, target_lines, f"ext{i}")
        files[fname] = src

    return SyntheticRepo(
        repo_id=f"inheritance_{size.value}",
        challenge="inheritance",
        size_tier=size,
        files=files,
        questions=questions,
        description="Deep class hierarchies with mixins to test MRO resolution and method override tracking",
    )
