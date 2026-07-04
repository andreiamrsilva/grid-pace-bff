"""
Test script for WRC API client endpoints.
Tests all available endpoints using event_id=635 and rally_id=703.
"""

import asyncio
import json
from pathlib import Path
from openwrc.clients.wrc_api_client import WrcApiClient

# Constants
EVENT_ID = 635
RALLY_ID = 703
OUTPUT_DIR = Path("scripts/api_test_outputs")


async def save_json(data, filename: str):
    """Save pydantic model or dict to JSON file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = OUTPUT_DIR / filename

    # Handle lists of Pydantic models
    if isinstance(data, list):
        # Convert each item in the list
        json_data = []
        for item in data:
            if hasattr(item, "model_dump"):
                json_data.append(item.model_dump(mode="json"))
            else:
                json_data.append(item)
        data = json_data
    # Convert single pydantic model to JSON string first, then parse back to dict
    # This ensures all nested models are properly serialized
    elif hasattr(data, "model_dump_json"):
        json_str = data.model_dump_json()
        data = json.loads(json_str)
    elif hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved: {filename}")


async def test_endpoints():
    """Test all WRC API client endpoints."""
    print(f"Testing WRC API endpoints with event_id={EVENT_ID}, rally_id={RALLY_ID}\n")

    async with WrcApiClient() as client:
        # 1. Get event metadata first (needed for other endpoints)
        print("1. Testing get_event_metadata...")
        try:
            event_metadata = await client.get_event_metadata(EVENT_ID)
            await save_json(event_metadata, "event_metadata.json")

            # Extract itinerary_id from rallies
            itinerary_ids = [rally.itinerary_id for rally in event_metadata.rallies]

            print(f"   Found {len(itinerary_ids)} itineraries from rallies\n")
        except Exception as e:
            print(f"✗ Error: {e}\n")
            return

        # 1b. Get first itinerary to extract stage and start list IDs
        print("1b. Getting itinerary details for stage/start list IDs...")
        stage_ids = []
        start_list_ids = []
        try:
            if itinerary_ids:
                first_itinerary_id = itinerary_ids[0]
                itinerary = await client.get_event_itineraries(
                    EVENT_ID, first_itinerary_id
                )

                # Extract stage and start list IDs from itinerary legs
                for leg in itinerary.itinerary_legs:
                    if leg.start_list_id:
                        start_list_ids.append(leg.start_list_id)
                    for section in leg.itinerary_sections:
                        for stage in section.stages:
                            stage_ids.append(stage.stage_id)

                print(
                    f"   Found {len(stage_ids)} stages, {len(start_list_ids)} start lists\n"
                )
        except Exception as e:
            print(f"✗ Error: {e}\n")

        # 2. Get itineraries
        print("2. Testing get_event_itineraries...")
        for itinerary_id in itinerary_ids[:2]:  # Test first 2 to avoid too many calls
            try:
                itinerary = await client.get_event_itineraries(EVENT_ID, itinerary_id)
                await save_json(itinerary, f"itinerary_{itinerary_id}.json")
            except Exception as e:
                print(f"✗ Error for itinerary {itinerary_id}: {e}")
        print()

        # 3. Get rally entries
        print("3. Testing get_rally_entries...")
        try:
            entries = await client.get_rally_entries(EVENT_ID, RALLY_ID)
            await save_json(entries, "rally_entries.json")
        except Exception as e:
            print(f"✗ Error: {e}")
        print()

        # 4. Get rally results
        print("4. Testing get_rally_results...")
        try:
            results = await client.get_rally_results(EVENT_ID, RALLY_ID)
            await save_json(results, "rally_results.json")
        except Exception as e:
            print(f"✗ Error: {e}")
        print()

        # 5. Get stage results (test last stage only)
        if stage_ids:
            stage_id = stage_ids[-1]
            print(f"5. Testing get_event_stage_results (stage_id={stage_id})...")
            try:
                stage_results = await client.get_event_stage_results(
                    EVENT_ID, stage_id, RALLY_ID
                )
                await save_json(stage_results, f"stage_results_{stage_id}.json")
            except Exception as e:
                print(f"✗ Error: {e}")
            print()

        # 6. Get stage time results
        if stage_ids:
            stage_id = stage_ids[-1]
            print(f"6. Testing get_event_stage_time_results (stage_id={stage_id})...")
            try:
                stage_times = await client.get_event_stage_time_results(
                    EVENT_ID, stage_id, RALLY_ID
                )
                await save_json(stage_times, f"stage_time_results_{stage_id}.json")
            except Exception as e:
                print(f"✗ Error: {e}")
            print()

        # 7. Get shakedown results
        print("7. Testing get_event_shakedown_results...")
        try:
            shakedown = await client.get_event_shakedown_results(
                EVENT_ID, shakedown_number=1
            )
            await save_json(shakedown, "shakedown_results.json")
        except Exception as e:
            print(f"✗ Error: {e}")
        print()

        # 8. Get split time results
        if stage_ids:
            stage_id = stage_ids[-1]
            print(
                f"8. Testing get_rally_stage_split_time_results (stage_id={stage_id})..."
            )
            try:
                split_times = await client.get_rally_stage_split_time_results(
                    EVENT_ID, RALLY_ID, stage_id
                )
                await save_json(split_times, f"split_time_results_{stage_id}.json")
            except Exception as e:
                print(f"✗ Error: {e}")
            print()

        # 9. Get start lists
        print("9. Testing get_event_start_list...")
        for start_list_id in start_list_ids[:2]:  # Test first 2
            try:
                start_list = await client.get_event_start_list(EVENT_ID, start_list_id)
                await save_json(start_list, f"start_list_{start_list_id}.json")
            except Exception as e:
                print(f"✗ Error for start_list {start_list_id}: {e}")
        print()

    print(f"\nAll tests complete! Results saved to {OUTPUT_DIR}/")


async def check_multiple_rallies_per_event():
    """
    Check if events can have multiple rallies by testing various event IDs in parallel.
    Also fetches detailed data for events with multiple rallies.
    """
    print("Checking if events can have multiple rallies...\n")

    # Test just a sample of event IDs across different time periods
    test_event_ids = [
        635,
        634,
        633,  # Recent 2025
        630,
        628,
        625,  # Late 2024
        600,
        595,
        590,  # Mid 2024
        555,  # 2023
    ]

    events_with_multiple_rallies = []

    async def check_event(client, event_id):
        """Check a single event and return its rally info."""
        try:
            event_metadata = await client.get_event_metadata(event_id)
            rally_count = len(event_metadata.rallies)

            return {
                "event_id": event_id,
                "name": event_metadata.name,
                "rally_count": rally_count,
                "rallies": [
                    {
                        "rally_id": r.rally_id,
                        "itinerary_id": r.itinerary_id,
                        "name": r.name,
                        "is_main": r.is_main,
                    }
                    for r in event_metadata.rallies
                ],
            }
        except Exception:
            return None

    async with WrcApiClient() as client:
        # Fetch all events in parallel
        results = await asyncio.gather(
            *[check_event(client, eid) for eid in test_event_ids]
        )

        # Filter out None results (failed requests)
        valid_results = [r for r in results if r is not None]

        # Print results
        for result in valid_results:
            print(f"Event {result['event_id']}: {result['name']}")
            print(f"  Rallies: {result['rally_count']}")

            if result["rally_count"] > 1:
                print("  ⚠️  MULTIPLE RALLIES FOUND!")
                events_with_multiple_rallies.append(result)
                for rally in result["rallies"]:
                    print(
                        f"     - rally_id={rally['rally_id']}, itinerary_id={rally['itinerary_id']}, name='{rally['name']}', is_main={rally['is_main']}"
                    )
            print()

        # For events with multiple rallies, fetch detailed data
        if events_with_multiple_rallies:
            print("\nFetching detailed data for events with multiple rallies...\n")

            for event in events_with_multiple_rallies:
                event_id = event["event_id"]
                print(f"Event {event_id}: {event['name']}")

                # Fetch entries and itineraries for each rally
                for rally in event["rallies"]:
                    rally_id = rally["rally_id"]
                    itinerary_id = rally["itinerary_id"]

                    try:
                        # Fetch entries
                        entries = await client.get_rally_entries(event_id, rally_id)
                        rally["entry_count"] = len(entries)
                        rally["sample_entry_ids"] = [e.entry_id for e in entries[:3]]

                        # Save entries to file
                        await save_json(
                            entries,
                            f"multi_rally_event_{event_id}_rally_{rally_id}_entries.json",
                        )
                        print(
                            f"  Rally {rally_id} ({rally['name']}): {len(entries)} entries"
                        )

                        # Fetch itinerary
                        itinerary = await client.get_event_itineraries(
                            event_id, itinerary_id
                        )
                        rally["itinerary_leg_count"] = len(itinerary.itinerary_legs)

                        # Count stages
                        stage_count = 0
                        for leg in itinerary.itinerary_legs:
                            for section in leg.itinerary_sections:
                                stage_count += len(section.stages)
                        rally["stage_count"] = stage_count

                        # Save itinerary to file
                        await save_json(
                            itinerary,
                            f"multi_rally_event_{event_id}_rally_{rally_id}_itinerary.json",
                        )
                        print(
                            f"    Itinerary: {rally['itinerary_leg_count']} legs, {stage_count} stages"
                        )

                    except Exception as e:
                        print(f"  Error fetching data for rally {rally_id}: {e}")

                # Check shakedown times to see if they're event-level or rally-specific
                print(f"\n  Checking shakedown times for event {event_id}...")
                try:
                    shakedown_times = await client.get_event_shakedown_results(
                        event_id, shakedown_number=1
                    )

                    # Get entry IDs from shakedown
                    shakedown_entry_ids = set(st.entry_id for st in shakedown_times)

                    # Check which rally each entry belongs to
                    rally_entry_ids = {}
                    for rally in event["rallies"]:
                        rally_entry_ids[rally["rally_id"]] = set(
                            rally.get("sample_entry_ids", [])
                        )

                    print(
                        f"  Shakedown has {len(shakedown_times)} times from {len(shakedown_entry_ids)} unique entries"
                    )

                    # Check overlap with each rally
                    for rally in event["rallies"]:
                        rally_id = rally["rally_id"]
                        # We need all entry IDs, not just samples
                        rally_entries = await client.get_rally_entries(
                            event_id, rally_id
                        )
                        all_rally_entry_ids = set(e.entry_id for e in rally_entries)

                        overlap = shakedown_entry_ids & all_rally_entry_ids
                        print(
                            f"    Rally {rally_id} ({rally['name']}): {len(overlap)} entries in shakedown out of {len(all_rally_entry_ids)} total"
                        )

                    # Save shakedown data
                    await save_json(
                        shakedown_times, f"multi_rally_event_{event_id}_shakedown.json"
                    )
                    event["shakedown_analysis"] = {
                        "total_entries": len(shakedown_entry_ids),
                        "total_times": len(shakedown_times),
                    }

                except Exception as e:
                    print(f"  Error fetching shakedown: {e}")

                print()

    # Save summary to JSON
    summary = {
        "checked_event_ids": test_event_ids,
        "events_checked": len(valid_results),
        "events_with_multiple_rallies": len(events_with_multiple_rallies),
        "all_results": valid_results,
        "multiple_rally_events": events_with_multiple_rallies,
    }

    await save_json(summary, "multi_rally_check_summary.json")

    print(f"{'='*60}")
    print(f"Summary: Checked {len(valid_results)} events")
    print(f"Events with multiple rallies: {len(events_with_multiple_rallies)}")

    if events_with_multiple_rallies:
        print(f"\n{'='*60}")
        print("⚠️  EVENTS WITH MULTIPLE RALLIES:")
        for event in events_with_multiple_rallies:
            print(f"\n  Event {event['event_id']}: {event['name']}")
            print(f"  Total rallies: {event['rally_count']}")
            for rally in event["rallies"]:
                print(
                    f"    - Rally {rally['rally_id']}: {rally['name']} (main={rally['is_main']})"
                )
                if "entry_count" in rally:
                    print(
                        f"      Entries: {rally['entry_count']}, Stages: {rally['stage_count']}, Legs: {rally['itinerary_leg_count']}"
                    )
    else:
        print("  ✅ All events have exactly 1 rally")
        print("  Conclusion: Event:Rally relationship appears to be 1:1")

    print(
        "\n✅ Results saved to scripts/api_test_outputs/multi_rally_check_summary.json"
    )
    print(f"{'='*60}\n")


async def check_split_point_correlation():
    """
    Check if split_point_id in split times corresponds to control_id in itinerary.
    This helps determine if we need a separate SplitPoint table or can use Control FK.
    """
    print("Checking split_point_id correlation with control_id...\n")

    event_id = 635
    rally_id = 703

    async with WrcApiClient() as client:
        # Get itinerary to find stage and control IDs
        print(f"Fetching itinerary for event {event_id}, rally {rally_id}...")
        event_metadata = await client.get_event_metadata(event_id)
        itinerary_id = event_metadata.rallies[0].itinerary_id
        itinerary = await client.get_event_itineraries(event_id, itinerary_id)

        # Extract stages and their controls
        stage_controls = {}
        for leg in itinerary.itinerary_legs:
            for section in leg.itinerary_sections:
                for stage in section.stages:
                    stage_controls[stage.stage_id] = []

                for control in section.controls:
                    if control.stage_id:
                        if control.stage_id not in stage_controls:
                            stage_controls[control.stage_id] = []
                        stage_controls[control.stage_id].append(
                            {
                                "control_id": control.control_id,
                                "code": control.code,
                                "type": control.type,
                                "location": control.location,
                            }
                        )

        # Get a stage with split times
        test_stage_id = None
        for stage_id in stage_controls.keys():
            if len(stage_controls[stage_id]) > 0:
                test_stage_id = stage_id
                break

        if not test_stage_id:
            print("No stages with controls found")
            return

        print(f"\nTesting stage {test_stage_id}...")
        print(f"Controls for this stage: {len(stage_controls[test_stage_id])}")
        for ctrl in stage_controls[test_stage_id][:5]:
            print(
                f"  - control_id={ctrl['control_id']}, code={ctrl['code']}, type={ctrl['type']}, location={ctrl['location']}"
            )

        # Get split times for this stage
        try:
            print(f"\nFetching split times for stage {test_stage_id}...")
            split_times = await client.get_rally_stage_split_time_results(
                event_id, rally_id, test_stage_id
            )

            if len(split_times) == 0:
                print("No split times found for this stage")
                return

            # Extract unique split_point_ids
            split_point_ids = set(st.split_point_id for st in split_times)
            print(f"Found {len(split_times)} split time records")
            print(f"Unique split_point_ids: {sorted(split_point_ids)}")

            # Sample split times
            print("\nSample split times:")
            for st in split_times[:3]:
                print(
                    f"  - entry_id={st.entry_id}, split_point_id={st.split_point_id}, elapsed_ms={st.elapsed_duration_ms}"
                )

            # Compare with control_ids
            control_ids = set(c["control_id"] for c in stage_controls[test_stage_id])
            print(f"\nControl IDs for this stage: {sorted(control_ids)}")

            # Check overlap
            overlap = split_point_ids & control_ids
            print(f"\n{'='*60}")
            print("Analysis:")
            print(f"  Split point IDs: {len(split_point_ids)}")
            print(f"  Control IDs: {len(control_ids)}")
            print(f"  Overlap: {len(overlap)}")

            if overlap == split_point_ids:
                print("\n✅ ALL split_point_ids match control_ids!")
                print("   → SplitTime.split_point_id can use FK to Control.control_id")
            elif len(overlap) > 0:
                print("\n⚠️  PARTIAL overlap")
                print(
                    f"   Split points not in controls: {split_point_ids - control_ids}"
                )
                print(
                    f"   Controls not in split points: {control_ids - split_point_ids}"
                )
            else:
                print(
                    "\n❌ NO overlap - split_point_id does NOT correspond to control_id"
                )
                print("   → Need separate SplitPoint table")

            print(f"{'='*60}\n")

            # Save data for analysis
            analysis = {
                "stage_id": test_stage_id,
                "control_count": len(control_ids),
                "control_ids": sorted(control_ids),
                "split_point_count": len(split_point_ids),
                "split_point_ids": sorted(split_point_ids),
                "overlap_count": len(overlap),
                "overlap_ids": sorted(overlap),
                "all_match": overlap == split_point_ids,
                "controls": stage_controls[test_stage_id],
            }

            await save_json(analysis, "split_point_analysis.json")
            print(
                "✅ Analysis saved to scripts/api_test_outputs/split_point_analysis.json"
            )

        except Exception as e:
            print(f"Error fetching split times: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--check-multiple-rallies":
        asyncio.run(check_multiple_rallies_per_event())
    elif len(sys.argv) > 1 and sys.argv[1] == "--check-split-points":
        asyncio.run(check_split_point_correlation())
    else:
        asyncio.run(test_endpoints())
