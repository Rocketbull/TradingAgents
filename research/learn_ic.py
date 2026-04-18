import numpy as np
import pandas as pd

def run_fundamental_law_sim(skills, breadths):
    results = []
    
    for skill_pct in skills:
        # Grinold's IC for binary bets is roughly: 2 * (accuracy - 0.5)
        # 55% accuracy = 0.10 IC
        ic_theory = 2 * (skill_pct - 0.5)
        
        for br in breadths:
            # 1. Theoretical Calculation
            ir_theory = ic_theory * np.sqrt(br)
            
            # 2. Simulation (Monte Carlo)
            # 1 = Win, 0 = Loss
            bets = np.random.choice([1, 0], size=br, p=[skill_pct, 1 - skill_pct])
            
            # Convert to 'Active Returns' (Win = +1%, Loss = -1%)
            returns = np.where(bets == 1, 0.01, -0.01)
            
            # 3. Post-Simulation Evaluation
            actual_alpha = np.mean(returns)
            actual_vol = np.std(returns) if np.std(returns) > 0 else 1
            ir_realized = (actual_alpha / actual_vol) * np.sqrt(br) if br > 1 else 0
            
            results.append({
                "Accuracy": f"{skill_pct:.0%}",
                "IC (Theory)": round(ic_theory, 2),
                "BR (Bets)": br,
                "IR (Theory)": round(ir_theory, 2),
                "IR (Realized)": round(ir_realized, 2),
                "Win Rate": f"{(np.sum(bets)/br):.1%}"
            })
            
    return pd.DataFrame(results)

# Parameters
skills_to_test = [0.50, 0.55, 0.60]
bets_to_test = [10, 100, 1000]

df_sim = run_fundamental_law_sim(skills_to_test, bets_to_test)
print(df_sim.to_string(index=False))