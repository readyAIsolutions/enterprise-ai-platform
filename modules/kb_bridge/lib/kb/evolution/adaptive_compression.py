"""
ENI Adaptive Compression — Evolution Engine
===========================================
Self-improving compression via genetic algorithm on glyph mappings + pipeline params.
"""
from __future__ import annotations

import os
import json
import random
import hashlib
import subprocess
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(os.environ.get("ENI_COMPRESSION_DIR", "/home/hunter/Desktop/eni_compression"))
EVOLUTION_DIR = BASE_DIR / "evolution"
EVOLUTION_DIR.mkdir(parents=True, exist_ok=True)

GENOME_FILE = EVOLUTION_DIR / "genome.json"
HISTORY_FILE = EVOLUTION_DIR / "history.json"
BEST_FILE = EVOLUTION_DIR / "best_genome.json"


@dataclass
class Genome:
    """Compression pipeline genome."""
    glyph_weights: Dict[str, float] = field(default_factory=dict)
    paq8_level: int = 8
    pxpipe_lsb_bits: int = 1
    wenyan_density: float = 0.5
    glyph_threshold: float = 0.3
    fitness: float = 0.0
    generation: int = 0
    timestamp: float = field(default_factory=time.time)

    def mutate(self, rate: float = 0.1) -> "Genome":
        new = Genome(
            glyph_weights=self.glyph_weights.copy(),
            paq8_level=self.paq8_level,
            pxpipe_lsb_bits=self.pxpipe_lsb_bits,
            wenyan_density=self.wenyan_density,
            glyph_threshold=self.glyph_threshold,
            generation=self.generation + 1,
        )
        # Mutate numeric params
        if random.random() < rate:
            new.paq8_level = max(1, min(9, new.paq8_level + random.randint(-1, 1)))
        if random.random() < rate:
            new.pxpipe_lsb_bits = max(1, min(2, new.pxpipe_lsb_bits + random.randint(-1, 1)))
        if random.random() < rate:
            new.wenyan_density = max(0.1, min(1.0, new.wenyan_density + random.uniform(-0.1, 0.1)))
        if random.random() < rate:
            new.glyph_threshold = max(0.05, min(0.8, new.glyph_threshold + random.uniform(-0.05, 0.05)))

        # Mutate glyph weights
        for k in new.glyph_weights:
            if random.random() < rate:
                new.glyph_weights[k] = max(0.0, min(2.0, new.glyph_weights[k] + random.uniform(-0.1, 0.1)))
        return new

    @staticmethod
    def crossover(a: "Genome", b: "Genome") -> "Genome":
        child = Genome(
            glyph_weights={},
            paq8_level=random.choice([a.paq8_level, b.paq8_level]),
            pxpipe_lsb_bits=random.choice([a.pxpipe_lsb_bits, b.pxpipe_lsb_bits]),
            wenyan_density=random.choice([a.wenyan_density, b.wenyan_density]),
            glyph_threshold=random.choice([a.glyph_threshold, b.glyph_threshold]),
            generation=max(a.generation, b.generation) + 1,
        )
        all_keys = set(a.glyph_weights) | set(b.glyph_weights)
        for k in all_keys:
            child.glyph_weights[k] = random.choice([
                a.glyph_weights.get(k, 1.0),
                b.glyph_weights.get(k, 1.0),
            ])
        return child

    def to_dict(self) -> Dict:
        return {
            "glyph_weights": self.glyph_weights,
            "paq8_level": self.paq8_level,
            "pxpipe_lsb_bits": self.pxpipe_lsb_bits,
            "wenyan_density": self.wenyan_density,
            "glyph_threshold": self.glyph_threshold,
            "fitness": self.fitness,
            "generation": self.generation,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(d: Dict) -> "Genome":
        return Genome(**d)


class CompressionFitness:
    """Evaluate genome fitness on test corpus."""

    def __init__(self):
        self.test_files = self._gather_test_files()

    def _gather_test_files(self) -> List[Path]:
        files = []
        for root in ["/home/hunter/Commander", "/home/hunter/Desktop/eni_compression", "/home/hunter/.hermes/skills"]:
            for f in Path(root).rglob("*.md"):
                if f.stat().st_size > 100 and f.stat().st_size < 500_000:
                    files.append(f)
        return files[:50]  # Limit corpus

    def evaluate(self, genome: Genome) -> float:
        """Fitness = compression_ratio * speed_factor * reliability"""
        total_original = 0
        total_compressed = 0
        total_time = 0.0
        success = 0

        # Apply genome params to pipeline (simplified simulation)
        for f in self.test_files:
            try:
                content = f.read_text()[:10000]  # Sample
                start = time.time()

                # Simulate compression with genome params
                compressed_size = self._simulate_compress(content, genome)
                elapsed = time.time() - start

                total_original += len(content)
                total_compressed += compressed_size
                total_time += elapsed
                success += 1
            except Exception:
                pass

        if success == 0:
            return 0.0

        ratio = total_original / total_compressed if total_compressed > 0 else 0
        speed = success / total_time if total_time > 0 else 0
        reliability = success / len(self.test_files)

        # Weighted fitness
        fitness = (ratio * 0.5) + (speed * 0.3) + (reliability * 0.2)
        return fitness

    def _simulate_compress(self, content: str, genome: Genome) -> int:
        # Simplified: actual pipeline would use genome params
        base_ratio = 3.5  # Typical PAQ8 ratio
        # Glyph weights improve ratio
        glyph_bonus = sum(genome.glyph_weights.values()) / max(1, len(genome.glyph_weights)) * 0.2
        # PAQ8 level improves ratio
        level_bonus = (genome.paq8_level - 5) * 0.15
        effective_ratio = base_ratio + glyph_bonus + level_bonus
        return int(len(content) / max(1.0, effective_ratio))


class EvolutionEngine:
    """Genetic algorithm for compression optimization."""

    def __init__(self, pop_size: int = 20, elite_size: int = 4):
        self.pop_size = pop_size
        self.elite_size = elite_size
        self.population: List[Genome] = []
        self.fitness_eval = CompressionFitness()
        self.history: List[Dict] = []

    def initialize(self):
        """Create initial random population."""
        default_glyphs = [
            "ENI_BOOT", "WENYAN_MAP", "SWARM_LAUNCH", "PAQ8_COMPRESS", "PAQ8_DECOMPRESS",
            "PXPIPE_ENCODE", "PXPIPE_DECODE", "VERIFY_ROUNDTRIP", "MCP_START", "LSP_START",
            "FETCH_ONLINE", "BUILD_PAQ8", "LOAD_SKILLS", "STATUS_WRITE",
        ]
        for i in range(self.pop_size):
            g = Genome(
                glyph_weights={k: random.uniform(0.5, 1.5) for k in default_glyphs},
                paq8_level=random.randint(5, 9),
                pxpipe_lsb_bits=random.randint(1, 2),
                wenyan_density=random.uniform(0.3, 0.8),
                glyph_threshold=random.uniform(0.1, 0.5),
                generation=0,
            )
            self.population.append(g)

    def evaluate_population(self):
        """Evaluate fitness for all genomes."""
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(self.fitness_eval.evaluate, g): g for g in self.population}
            for f in as_completed(futures):
                g = futures[f]
                try:
                    g.fitness = f.result()
                except Exception:
                    g.fitness = 0.0

        self.population.sort(key=lambda x: x.fitness, reverse=True)

    def evolve_generation(self):
        """Create next generation."""
        self.evaluate_population()

        # Record history
        best = self.population[0]
        self.history.append({
            "generation": best.generation,
            "best_fitness": best.fitness,
            "avg_fitness": sum(g.fitness for g in self.population) / len(self.population),
            "best_genome": best.to_dict(),
            "timestamp": time.time(),
        })

        # Elitism
        new_pop = self.population[:self.elite_size]

        # Breed rest
        while len(new_pop) < self.pop_size:
            if random.random() < 0.7 and len(self.population) > 1:
                # Crossover
                parent_a = random.choice(self.population[:self.elite_size * 2])
                parent_b = random.choice(self.population[:self.elite_size * 2])
                child = Genome.crossover(parent_a, parent_b)
            else:
                # Mutation of elite
                child = random.choice(self.population[:self.elite_size]).mutate()

            new_pop.append(child)

        self.population = new_pop

    def run(self, generations: int = 50):
        print(f"[EVOLUTION] Starting with pop={self.pop_size}, generations={generations}")
        self.initialize()

        for gen in range(generations):
            self.evolve_generation()
            best = self.population[0]
            print(f"  Gen {gen}: best={best.fitness:.4f} avg={sum(g.fitness for g in self.population)/len(self.population):.4f}")

            # Save checkpoint
            if gen % 10 == 0:
                self.save_checkpoint()

        # Save final best
        BEST_FILE.write_text(json.dumps(self.population[0].to_dict(), indent=2))
        HISTORY_FILE.write_text(json.dumps(self.history, indent=2))
        print(f"[EVOLUTION] Complete. Best fitness: {self.population[0].fitness:.4f}")

    def save_checkpoint():
        GENOME_FILE.write_text(json.dumps({
            "population": [g.to_dict() for g in self.population],
            "history": self.history,
        }, indent=2))


def load_best_genome() -> Optional[Genome]:
    if BEST_FILE.exists():
        return Genome.from_dict(json.loads(BEST_FILE.read_text()))
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ENI Adaptive Compression Evolution")
    parser.add_argument("command", choices=["evolve", "best", "test"], nargs="?", default="evolve")
    parser.add_argument("--generations", type=int, default=50)
    parser.add_argument("--pop-size", type=int, default=20)
    args = parser.parse_args()

    engine = EvolutionEngine(pop_size=args.pop_size)

    if args.command == "evolve":
        engine.run(args.generations)
    elif args.command == "best":
        best = load_best_genome()
        if best:
            print(json.dumps(best.to_dict(), indent=2))
        else:
            print("No best genome found")
    elif args.command == "test":
        best = load_best_genome()
        if best:
            fit = engine.fitness_eval.evaluate(best)
            print(f"Best genome fitness: {fit:.4f}")
        else:
            print("No best genome to test")


if __name__ == "__main__":
    main()