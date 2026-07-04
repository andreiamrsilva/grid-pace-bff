# Scripts

This folder contains one-time utility scripts for testing and development purposes.

## API Testing Scripts

### `test_api_endpoints.py`

Tests all WRC API client endpoints and saves responses to JSON files for reference.

**Usage:**
```bash
python scripts/test_api_endpoints.py
```

**What it does:**
- Tests all 10 endpoints in `WrcApiClient`
- Uses event_id=635 and rally_id=703 as test data
- Automatically extracts required IDs (itinerary_id, stage_id, start_list_id) from metadata
- Saves each response to an individual JSON file in `scripts/api_test_outputs/`
- Handles errors gracefully and continues testing other endpoints

**Output files:**
- `event_metadata.json` - Basic event information and rally metadata
- `itinerary_{id}.json` - Complete itinerary with legs, sections, stages, and controls
- `rally_entries.json` - All entries (drivers, teams, cars) for the rally
- `rally_results.json` - Overall rally standings
- `stage_results_{stage_id}.json` - Results for a specific stage
- `stage_time_results_{stage_id}.json` - Stage time results for a specific stage
- `shakedown_results.json` - Shakedown stage times
- `split_time_results_{stage_id}.json` - Split times within a stage
- `start_list_{id}.json` - Start order and times for rally legs

**Note:** The `api_test_outputs/` folder is git-ignored as these are reference files that can be regenerated at any time.
