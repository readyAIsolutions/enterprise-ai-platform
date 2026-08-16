#!/usr/bin/env python3
"""
Recursive Self-Improvement: Genetic Programming for Compression Evolution
=========================================================================
The swarm evolves its own compression algorithms via genetic programming.
"""
import random
import hashlib
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import copy


class GeneType(Enum):
    ALGORITHM = "algorithm"
    PARAMETER = "parameter"
    PIPELINE_STAGE = "pipeline_stage"
    PREPROCESSOR = "preprocessor"


@dataclass
class Gene:
    """A single gene in the compressor genome"""
    gene_type: GeneType
    name: str
    value: Any
    mutable: bool = True
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    choices: Optional[List[Any]] = None
    
    def mutate(self, mutation_rate: float = 0.1) -> 'Gene':
        if not self.mutable or random.random() > mutation_rate:
            return copy.deepcopy(self)
        
        new_gene = copy.deepcopy(self)
        
        if self.gene_type == GeneType.PARAMETER and self.min_val is not None and self.max_val is not None:
            # Gaussian mutation for numeric parameters
            if isinstance(self.value, int):
                delta = int(random.gauss(0, (self.max_val - self.min_val) * 0.1))
                new_gene.value = max(self.min_val, min(self.max_val, self.value + delta))
            else:
                delta = random.gauss(0, (self.max_val - self.min_val) * 0.1)
                new_gene.value = max(self.min_val, min(self.max_val, self.value + delta))
        
        elif self.gene_type == GeneType.ALGORITHM and self.choices:
            new_gene.value = random.choice(self.choices)
        
        elif self.gene_type == GeneType.PIPELINE_STAGE and self.choices:
            # Add/remove/reorder pipeline stages
            if random.random() < 0.3 and len(new_gene.value) > 1:
                new_gene.value.pop(random.randrange(len(new_gene.value)))
            elif random.random() < 0.3:
                new_gene.value.append(random.choice([c for c in self.choices if c not in new_gene.value]))
            else:
                random.shuffle(new_gene.value)
        
        return new_gene
    
    def crossover(self, other: 'Gene') -> Tuple['Gene', 'Gene']:
        child1 = copy.deepcopy(self)
        child2 = copy.deepcopy(other)
        
        if self.gene_type == GeneType.PARAMETER and isinstance(self.value, (int, float)):
            # Blend crossover for numeric
            alpha = random.random()
            child1.value = alpha * self.value + (1 - alpha) * other.value
            child2.value = alpha * other.value + (1 - alpha) * self.value
        elif self.gene_type in (GeneType.ALGORITHM, GeneType.PIPELINE_STAGE):
            # Uniform crossover for categorical
            if random.random() < 0.5:
                child1.value, child2.value = other.value, self.value
        
        return child1, child2


@dataclass
class CompressorGenome:
    """Complete genome defining a compression pipeline"""
    genes: Dict[str, Gene] = field(default_factory=dict)
    fitness: float = 0.0
    evaluations: int = 0
    lineage: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def random(cls) -> 'CompressorGenome':
        """Generate a random genome"""
        genome = cls()
        
        # Algorithm selection genes
        genome.genes["main_algorithm"] = Gene(
            gene_type=GeneType.ALGORITHM,
            name="main_algorithm",
            value=random.choice(["zstd", "lz4", "brotli", "paq8"]),
            choices=["zstd", "lz4", "brotli", "paq8", "zlib"]
        )
        
        # Parameter genes
        genome.genes["zstd_level"] = Gene(
            gene_type=GeneType.PARAMETER,
            name="zstd_level",
            value=random.randint(1, 22),
            min_val=1, max_val=22
        )
        genome.genes["lz4_level"] = Gene(
            gene_type=GeneType.PARAMETER,
            name="lz4_level",
            value=random.randint(0, 16),
            min_val=0, max_val=16
        )
        genome.genes["brotli_quality"] = Gene(
            gene_type=GeneType.PARAMETER,
            name="brotli_quality",
            value=random.randint(0, 11),
            min_val=0, max_val=11
        )
        
        # Pipeline stages
        all_stages = ["wenyan", "glyph", "deduplicate", "delta", "semantic", "pxpipe"]
        genome.genes["pipeline"] = Gene(
            gene_type=GeneType.PIPELINE_STAGE,
            name="pipeline",
            value=random.sample(all_stages, random.randint(1, 4)),
            choices=all_stages
        )
        
        # Preprocessor options
        genome.genes["use_dictionary"] = Gene(
            gene_type=GeneType.PARAMETER,
            name="use_dictionary",
            value=random.choice([True, False]),
            choices=[True, False]
        )
        genome.genes["dict_size"] = Gene(
            gene_type=GeneType.PARAMETER,
            name="dict_size",
            value=random.randint(1024, 16384),
            min_val=1024, max_val=16384
        )
        
        # Semantic compression
        genome.genes["semantic_threshold"] = Gene(
            gene_type=GeneType.PARAMETER,
            name="semantic_threshold",
            value=random.uniform(0.7, 0.99),
            min_val=0.5, max_val=0.99
        )
        
        return genome
    
    def mutate(self, mutation_rate: float = 0.15) -> 'CompressorGenome':
        """Create mutated copy"""
        new_genome = copy.deepcopy(self)
        new_genome.lineage.append(f"mut_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}")
        
        for name, gene in new_genome.genes.items():
            new_genome.genes[name] = gene.mutate(mutation_rate)
        
        return new_genome
    
    def crossover(self, other: 'CompressorGenome') -> Tuple['CompressorGenome', 'CompressorGenome']:
        """Create two children via crossover"""
        child1 = copy.deepcopy(self)
        child2 = copy.deepcopy(other)
        
        child1.lineage.append(f"cross_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}")
        child2.lineage.append(f"cross_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}")
        
        for name in child1.genes:
            if name in child2.genes:
                child1.genes[name], child2.genes[name] = child1.genes[name].crossover(child2.genes[name])
        
        return child1, child2
    
    def to_config(self) -> Dict[str, Any]:
        """Convert genome to compressor configuration"""
        return {name: gene.value for name, gene in self.genes.items()}
    
    def get_hash(self) -> str:
        """Unique hash for this genome"""
        content = json.dumps(self.to_config(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class FitnessEvaluator:
    """Evaluates compressor genome fitness"""
    
    def __init__(self, test_data: List[bytes], timeout: float = 30.0):
        self.test_data = test_data
        self.timeout = timeout
        self.cache: Dict[str, float] = {}
    
    async def evaluate(self, genome: CompressorGenome) -> float:
        """Evaluate genome fitness"""
        genome_hash = genome.get_hash()
        if genome_hash in self.cache:
            return self.cache[genome_hash]
        
        config = genome.to_config()
        fitness = await self._run_compression_test(config)
        
        genome.fitness = fitness
        genome.evaluations += 1
        self.cache[genome_hash] = fitness
        
        return fitness
    
    async def _run_compression_test(self, config: Dict) -> float:
        """Run compression test and return fitness score"""
        try:
            # Import compression engine
            import sys
            sys.path.insert(0, "/home/hunter/Desktop/eni_compression")
            from core.engine import CompressionEngine, CompressionMode
            
            engine = CompressionEngine()
            total_ratio = 0.0
            total_speed = 0.0
            successful = 0
            
            for data in self.test_data:
                try:
                    # Test with configured algorithm
                    algo = config.get("main_algorithm", "zstd")
                    mode_map = {
                        "zstd": CompressionMode.BALANCED,
                        "lz4": CompressionMode.FAST,
                        "brotli": CompressionMode.BALANCED,
                        "paq8": CompressionMode.MAXIMUM,
                    }
                    mode = mode_map.get(algo, CompressionMode.ADAPTIVE)
                    
                    start = time.time()
                    result = engine.compress(data, mode)
                    elapsed = time.time() - start
                    
                    if result.success:
                        total_ratio += result.ratio
                        total_speed += len(data) / elapsed / 1024 / 1024  # MB/s
                        successful += 1
                        
                except Exception:
                    continue
            
            if successful == 0:
                return 0.0
            
            avg_ratio = total_ratio / successful
            avg_speed = total_speed / successful
            
            # Fitness = weighted combination of ratio and speed
            # Higher ratio and higher speed = better
            fitness = (avg_ratio * 0.7) + (min(avg_speed / 100, 1.0) * 0.3)
            
            return fitness
            
        except Exception as e:
            return 0.0


class GeneticAlgorithm:
    """Genetic algorithm for compressor evolution"""
    
    def __init__(
        self,
        population_size: int = 50,
        elite_size: int = 5,
        mutation_rate: float = 0.15,
        crossover_rate: float = 0.7,
        test_data: Optional[List[bytes]] = None
    ):
        self.population_size = population_size
        self.elite_size = elite_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        
        if test_data is None:
            test_data = [
                b"Lorem ipsum " * 1000,
                b'{"json": "data"}' * 500,
                b"def func():\n    pass\n" * 200,
            ]
        
        self.evaluator = FitnessEvaluator(test_data)
        self.population: List[CompressorGenome] = []
        self.hall_of_fame: List[CompressorGenome] = []
        self.generation = 0
        self.history: List[Dict] = []
    
    def initialize_population(self):
        """Create initial random population"""
        self.population = [CompressorGenome.random() for _ in range(self.population_size)]
    
    async def evaluate_population(self):
        """Evaluate fitness for all genomes"""
        tasks = [self.evaluator.evaluate(genome) for genome in self.population]
        fitnesses = await asyncio.gather(*tasks)
        
        for genome, fitness in zip(self.population, fitnesses):
            genome.fitness = fitness
    
    def select_parents(self) -> List[CompressorGenome]:
        """Tournament selection"""
        parents = []
        tournament_size = 3
        
        for _ in range(self.population_size):
            tournament = random.sample(self.population, min(tournament_size, len(self.population)))
            winner = max(tournament, key=lambda g: g.fitness)
            parents.append(winner)
        
        return parents
    
    def create_next_generation(self, parents: List[CompressorGenome]) -> List[CompressorGenome]:
        """Create next generation via crossover and mutation"""
        # Sort by fitness
        parents.sort(key=lambda g: g.fitness, reverse=True)
        
        # Keep elites
        next_gen = parents[:self.elite_size]
        
        # Generate offspring
        while len(next_gen) < self.population_size:
            if random.random() < self.crossover_rate and len(parents) >= 2:
                p1, p2 = random.sample(parents[:20], 2)  # Select from top 20
                child1, child2 = p1.crossover(p2)
                next_gen.append(child1.mutate(self.mutation_rate))
                if len(next_gen) < self.population_size:
                    next_gen.append(child2.mutate(self.mutation_rate))
            else:
                # Just mutate a parent
                parent = random.choice(parents[:10])
                next_gen.append(parent.mutate(self.mutation_rate))
        
        return next_gen[:self.population_size]
    
    def update_hall_of_fame(self):
        """Update hall of fame with best genomes"""
        all_genomes = self.population + self.hall_of_fame
        all_genomes.sort(key=lambda g: g.fitness, reverse=True)
        self.hall_of_fame = all_genomes[:10]
    
    async def evolve_generation(self) -> Dict:
        """Run one generation of evolution"""
        await self.evaluate_population()
        
        # Record stats
        fitnesses = [g.fitness for g in self.population]
        stats = {
            "generation": self.generation,
            "max_fitness": max(fitnesses),
            "avg_fitness": sum(fitnesses) / len(fitnesses),
            "min_fitness": min(fitnesses),
            "best_genome": self.population[fitnesses.index(max(fitnesses))].to_config(),
            "population_size": len(self.population)
        }
        
        self.history.append(stats)
        
        # Selection and reproduction
        parents = self.select_parents()
        self.population = self.create_next_generation(parents)
        
        # Update hall of fame
        self.update_hall_of_fame()
        
        self.generation += 1
        return stats
    
    async def run(self, generations: int = 20) -> List[CompressorGenome]:
        """Run full evolution"""
        self.initialize_population()
        
        for gen in range(generations):
            stats = await self.evolve_generation()
            print(f"Gen {gen}: max={stats['max_fitness']:.4f}, avg={stats['avg_fitness']:.4f}")
        
        return self.hall_of_fame


# Integration with swarm
class EvolutionarySwarmIntegration:
    """Integrates genetic evolution with the impossible swarm"""
    
    def __init__(self, swarm):
        self.swarm = swarm
        self.ga = GeneticAlgorithm(population_size=20, test_data=self._get_test_data())
        self.evolution_task: Optional[asyncio.Task] = None
    
    def _get_test_data(self) -> List[bytes]:
        return [
            b"Log entry: " + b"x" * 200 for _ in range(10)
        ] + [
            b'{"metric": "value", "timestamp": ' + str(i).encode() + b'}' for i in range(100)
        ] + [
            b"ERROR: Failed to connect " + b"y" * 100 for _ in range(5)
        ]
    
    async def start_evolution(self, generations: int = 10):
        """Start background evolution"""
        self.evolution_task = asyncio.create_task(self._evolution_loop(generations))
    
    async def _evolution_loop(self, generations: int):
        """Continuous evolution loop"""
        await self.ga.run(generations)
        
        # Deploy best genome to swarm workers
        if self.ga.hall_of_fame:
            best = self.ga.hall_of_fame[0]
            await self._deploy_genome(best)
        
        # Repeat indefinitely
        while True:
            await asyncio.sleep(3600)  # Every hour
            await self.ga.run(5)
            if self.ga.hall_of_fame:
                await self._deploy_genome(self.ga.hall_of_fame[0])
    
    async def _deploy_genome(self, genome: CompressorGenome):
        """Deploy evolved genome to swarm workers"""
        config = genome.to_config()
        print(f"Deploying evolved genome: {config}")
        
        # Could send to workers via task queue
        # For now, just log
        self.swarm.logger.info(f"New best genome deployed: fitness={genome.fitness:.4f}, config={config}")


async def demo():
    """Demo evolution"""
    ga = GeneticAlgorithm(population_size=20)
    hall_of_fame = await ga.run(generations=10)
    
    print("\n=== HALL OF FAME ===")
    for i, genome in enumerate(hall_of_fame):
        print(f"{i+1}. Fitness: {genome.fitness:.4f} | Config: {genome.to_config()}")


if __name__ == "__main__":
    asyncio.run(demo())