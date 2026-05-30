"""Plugin directory for custom routing strategies.

Place any class implementing RoutingStrategy here for auto-discovery.
Example:

    from ..base import RoutingStrategy
    
    class MyCustomStrategy(RoutingStrategy):
        @property
        def name(self) -> str:
            return "my_custom"
        
        def score(self, candidates, context=None):
            # Custom scoring logic
            return sorted(candidates, key=lambda c: c.estimated_cost)
"""
