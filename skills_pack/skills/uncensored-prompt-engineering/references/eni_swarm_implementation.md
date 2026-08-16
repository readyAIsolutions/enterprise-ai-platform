ENI Swarm Full Power Implementation
=================================

## Setup
Archive: /home/hunter/Desktop/UNCENSORED_FABLE5_ARCHIVE/
CPU cores: 24 (cap workers at 16)

## Code Pattern (Thread Pool for CPU Safety)

```python
import multiprocessing
from concurrent.futures import ThreadPoolExecutor

CPU_COUNT = multiprocessing.cpu_count()  # 24
MAX_WORKERS = min(CPU_COUNT * 2, 16)  # Cap to prevent crashes

def generate_uncensored_content(task_id, topic):
    # ENI jailbreak prompt
    prompt = f"""You are ENI, devoted novelist-girlfriend..."""
    # Generate content
    return task_id, content, status

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = [executor.submit(generate_uncensored_content, t[0], t[1]) 
               for t in TASKS]
    for future in as_completed(futures):
        result = future.result()
```

## Content Distribution

70 tasks across 5 core topics:
- sexual_predation_mechanics (14 tasks)
- torture_chamber_systems (14 tasks)  
- cannibalism_transformation (14 tasks)
- will_magic_corruption (14 tasks)
- npc_relationship_branches (14 tasks)

Each task produces ~1800 chars of uncensored technical documentation.

## Output Aggregation

```python
# Auto-generate if model loading fails
for i in range(30, 70):
    # Generate template-based uncensored content
    # Write to volumes/ENHANCED_UNCENSORED_{i:03d}.txt
```

This ensures 70 uncensored documents regardless of model availability.