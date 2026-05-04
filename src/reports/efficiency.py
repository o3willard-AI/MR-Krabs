"""
TierEfficiencyAnalysis module for cost-optimization analysis.

P4-5: Daily Cost Reporting - Tier Efficiency Analysis
========================================================

This module provides analysis of tier efficiency to help identify:
- Overused tiers (should be upgraded)
- Underused tiers (could be leveraged more)
- Cost-efficient tiers
- Optimization opportunities
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Dict, Any


@dataclass
class TierEfficiencyAnalysis:
    """
    Analysis results for a single tier's efficiency.
    
    Attributes:
        tier_name: Name of the tier (e.g., "L0-Coder")
        usage_count: Number of tasks handled by this tier
        total_cost: Total cost incurred by this tier
        avg_cost_per_task: Average cost per task
        success_rate: Percentage of successful tasks
        efficiency_score: Overall efficiency score (0-100)
    """
    tier_name: str
    usage_count: int
    total_cost: Decimal
    avg_cost_per_task: Decimal
    success_rate: Decimal
    efficiency_score: int


class TierEfficiencyAnalyzer:
    """
    Analyzer for calculating and reporting tier efficiency metrics.
    
    Provides methods to:
    - Analyze individual tier efficiency
    - Compare multiple tiers
    - Generate optimization suggestions
    - Identify over/underused tiers
    """
    
    # Cost thresholds for efficiency scoring
    LOW_COST_THRESHOLD = Decimal("0.10")  # < $0.10 per task is excellent
    HIGH_COST_THRESHOLD = Decimal("1.00")  # > $1.00 per task is expensive
    
    # Success rate benchmarks
    EXCELLENT_SUCCESS_RATE = Decimal("0.98")  # 98% or better
    MINIMUM_SUCCESS_RATE = Decimal("0.80")  # 80% minimum acceptable
    
    # Usage distribution thresholds
    OVERUSED_THRESHOLD = Decimal("0.70")  # Tier handles >70% of all tasks
    UNDERUSED_THRESHOLD = Decimal("0.05")  # Tier handles <5% of all tasks
    
    def analyze_tier_efficiency(self, tier_data: Dict[str, Any], tier_name: str = "Unknown") -> TierEfficiencyAnalysis:
        """
        Analyze efficiency for a single tier.
        
        Args:
            tier_data: Dictionary with keys:
                - count: Number of tasks
                - cost: Total cost (Decimal)
                - success_count: Number of successful tasks
            tier_name: Name of the tier
        
        Returns:
            TierEfficiencyAnalysis object with metrics
        """
        count = tier_data.get("count", 0)
        total_cost = tier_data.get("cost", Decimal("0.00"))
        success_count = tier_data.get("success_count", 0)
        
        # Calculate metrics
        avg_cost = total_cost / Decimal(count) if count > 0 else Decimal("0.00")
        success_rate = Decimal(success_count) / Decimal(count) if count > 0 else Decimal("0.00")
        
        # Calculate efficiency score
        efficiency_score = self._calculate_efficiency_score(avg_cost, success_rate)
        
        return TierEfficiencyAnalysis(
            tier_name=tier_name,
            usage_count=count,
            total_cost=total_cost,
            avg_cost_per_task=avg_cost,
            success_rate=success_rate,
            efficiency_score=efficiency_score
        )
    
    def analyze_all_tiers(self, tier_data: Dict[str, Dict]) -> List[TierEfficiencyAnalysis]:
        """
        Analyze efficiency for all tiers.
        
        Args:
            tier_data: Dictionary mapping tier names to tier data dicts
        
        Returns:
            List of TierEfficiencyAnalysis objects
        """
        analyses = []
        
        for tier_name, data in tier_data.items():
            analysis = self.analyze_tier_efficiency(data, tier_name)
            analyses.append(analysis)
        
        return analyses
    
    def _calculate_efficiency_score(self, avg_cost_per_task: Decimal, 
                                    success_rate: Decimal) -> int:
        """
        Calculate efficiency score based on cost and success rate.
        
        Scoring:
        - Base score: 40 points
        - Cost component (up to 30 points): Lower cost = higher score
        - Success component (up to 30 points): Higher success rate = higher score
        
        Args:
            avg_cost_per_task: Average cost per task
            success_rate: Success rate (0-1)
        
        Returns:
            Efficiency score (0-100)
        """
        score = 40  # Base score
        
        # Cost component (0-30 points)
        if avg_cost_per_task <= self.LOW_COST_THRESHOLD:
            score += 30
        elif avg_cost_per_task >= self.HIGH_COST_THRESHOLD:
            score += 3
        else:
            # Linear interpolation
            cost_ratio = (self.HIGH_COST_THRESHOLD - avg_cost_per_task) / \
                        (self.HIGH_COST_THRESHOLD - self.LOW_COST_THRESHOLD)
            score += int(27 * cost_ratio) + 3
        
        # Success component (0-30 points) - more aggressive penalty for low success
        if success_rate >= self.EXCELLENT_SUCCESS_RATE:
            score += 30
        elif success_rate < self.MINIMUM_SUCCESS_RATE:
            # Penalize heavily for low success rates
            low_success_penalty = (self.MINIMUM_SUCCESS_RATE - success_rate) * 100
            score += max(0, int(15 - low_success_penalty))
        else:
            # Linear interpolation
            success_ratio = (success_rate - self.MINIMUM_SUCCESS_RATE) / \
                           (self.EXCELLENT_SUCCESS_RATE - self.MINIMUM_SUCCESS_RATE)
            score += int(15 * success_ratio) + 15
        
        return min(100, max(0, score))
    
    def get_optimization_suggestions(self, 
                                     analyses: List[TierEfficiencyAnalysis]) -> List[Dict[str, Any]]:
        """
        Generate optimization suggestions based on efficiency analysis.
        
        Args:
            analyses: List of TierEfficiencyAnalysis objects
        
        Returns:
            List of suggestion dictionaries with tier, message, and priority
        """
        suggestions = []
        
        # Sort by usage for context
        total_usage = sum(a.usage_count for a in analyses)
        
        for analysis in analyses:
            # Check for overuse
            usage_ratio = Decimal(analysis.usage_count) / Decimal(total_usage) if total_usage > 0 else Decimal("0")
            
            if usage_ratio > self.OVERUSED_THRESHOLD:
                suggestions.append({
                    "tier": analysis.tier_name,
                    "message": f"Tier '{analysis.tier_name}' handles {usage_ratio:.0%} of all tasks. "
                              f"Consider distributing workload to other tiers to reduce cost.",
                    "priority": "high",
                    "type": "overuse"
                })
            
            # Check for underuse of higher-tier systems
            if analysis.efficiency_score > 85 and analysis.usage_count < total_usage * 0.05:
                suggestions.append({
                    "tier": analysis.tier_name,
                    "message": f"Tier '{analysis.tier_name}' has high efficiency (score: {analysis.efficiency_score}). "
                              f"Could handle more complex tasks from lower tiers.",
                    "priority": "low",
                    "type": "optimization"
                })
            
            # Check for high cost
            if analysis.avg_cost_per_task > self.HIGH_COST_THRESHOLD:
                suggestions.append({
                    "tier": analysis.tier_name,
                    "message": f"Tier '{analysis.tier_name}' has high average cost: "
                              f"${analysis.avg_cost_per_task:.3f}/task. Consider if lower tiers can handle these tasks.",
                    "priority": "medium",
                    "type": "cost"
                })
            
            # Check for low success rate
            if analysis.success_rate < self.MINIMUM_SUCCESS_RATE:
                suggestions.append({
                    "tier": analysis.tier_name,
                    "message": f"Tier '{analysis.tier_name}' has low success rate: "
                              f"{analysis.success_rate:.0%}. May need configuration tuning.",
                    "priority": "high",
                    "type": "success_rate"
                })
        
        # Sort suggestions by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        return suggestions
    
    def identify_overused_tiers(self, 
                                analyses: List[TierEfficiencyAnalysis], 
                                threshold: Decimal = OVERUSED_THRESHOLD) -> List[TierEfficiencyAnalysis]:
        """
        Identify tiers that are handling disproportionate workload.
        
        Args:
            analyses: List of TierEfficiencyAnalysis objects
            threshold: Usage ratio threshold (default 0.70 = 70%)
        
        Returns:
            List of overused tier analyses
        """
        total_usage = sum(a.usage_count for a in analyses)
        overused = []
        
        for analysis in analyses:
            if total_usage > 0:
                usage_ratio = Decimal(analysis.usage_count) / Decimal(total_usage)
                if usage_ratio > threshold:
                    overused.append(analysis)
        
        return overused
    
    def identify_underused_tiers(self, 
                                 analyses: List[TierEfficiencyAnalysis],
                                 threshold: Decimal = UNDERUSED_THRESHOLD) -> List[TierEfficiencyAnalysis]:
        """
        Identify tiers that are underutilized.
        
        Args:
            analyses: List of TierEfficiencyAnalysis objects
            threshold: Usage ratio threshold (default 0.05 = 5%)
        
        Returns:
            List of underused tier analyses
        """
        total_usage = sum(a.usage_count for a in analyses)
        underused = []
        
        for analysis in analyses:
            if total_usage > 0:
                usage_ratio = Decimal(analysis.usage_count) / Decimal(total_usage)
                if usage_ratio < threshold and analysis.usage_count > 0:
                    underused.append(analysis)
        
        return underused
    
    def rank_by_efficiency(self, 
                           analyses: List[TierEfficiencyAnalysis]) -> List[TierEfficiencyAnalysis]:
        """
        Rank tiers by efficiency score (highest first).
        
        Args:
            analyses: List of TierEfficiencyAnalysis objects
        
        Returns:
            List sorted by efficiency_score descending
        """
        return sorted(analyses, key=lambda x: x.efficiency_score, reverse=True)
    
    def get_summary_report(self, analyses: List[TierEfficiencyAnalysis]) -> Dict[str, Any]:
        """
        Generate a summary report of tier efficiency.
        
        Args:
            analyses: List of TierEfficiencyAnalysis objects
        
        Returns:
            Summary dictionary with key metrics
        """
        if not analyses:
            return {"error": "No analyses provided"}
        
        total_cost = sum(a.total_cost for a in analyses)
        total_tasks = sum(a.usage_count for a in analyses)
        
        # Find best and worst tiers
        best_tier = max(analyses, key=lambda x: x.efficiency_score)
        worst_tier = min(analyses, key=lambda x: x.efficiency_score)
        
        return {
            "total_cost": total_cost,
            "total_tasks": total_tasks,
            "avg_cost_per_task": total_cost / Decimal(total_tasks) if total_tasks > 0 else Decimal("0.00"),
            "best_tier": {
                "name": best_tier.tier_name,
                "efficiency_score": best_tier.efficiency_score,
                "avg_cost_per_task": best_tier.avg_cost_per_task
            },
            "worst_tier": {
                "name": worst_tier.tier_name,
                "efficiency_score": worst_tier.efficiency_score,
                "avg_cost_per_task": worst_tier.avg_cost_per_task
            },
            "tier_count": len(analyses),
            "overused_tiers": self.identify_overused_tiers(analyses),
            "underused_tiers": self.identify_underused_tiers(analyses)
        }
