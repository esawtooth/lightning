if __name__ == "__main__":
    import logging
    from lightning_core.planner.pipeline import create_verified_plan
    logging.basicConfig(level=logging.INFO)
    plan_bundle = create_verified_plan(
        instruction="Every Monday, collect unread HR mails "
                    "and send me a one‑paragraph summary in Teams",
        user_id="user_xyz",
        registry_query="email"
    )
    print("✅ Verified plan stored:", plan_bundle["plan_id"])
    print(plan_bundle["plan"])
