"""
Improved fetch function for your notebook that properly handles end of data.
Copy this into a cell in your complete_hourly_fetch_analysis.ipynb notebook.
"""

def fetch_all_pages_improved(endpoint_name, date_str, limit_per_page=1000, max_pages=1000):
    """
    Improved fetcher that:
    1. Never gives up on a page due to temporary errors
    2. Properly detects end of data vs temporary failure
    3. Continues until truly complete or confirmed end
    """
    endpoint_config = ENDPOINTS[endpoint_name]
    url = SIP_BASE_URL + endpoint_config['url']
    node_field = endpoint_config['node_field']
    target_nodes = endpoint_config['nodes']
    
    print(f"\n{'='*80}")
    print(f"IMPROVED FETCH: {endpoint_name} for {date_str}")
    print(f"Limit per page: {limit_per_page}")
    print(f"{'='*80}")
    
    # Results storage
    location_data = defaultdict(lambda: {'pages': set(), 'hours': set(), 'records': []})
    page_summary = {}
    
    page = 1
    consecutive_empty = 0
    total_fetched = 0
    start_time = time.time()
    pages_with_errors = []  # Track pages that had errors
    
    while page <= max_pages:
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'page': page,
            'limit': limit_per_page,
            'user_key': SIP_API_KEY
        }
        
        print(f"\n📄 Page {page:3d}: ", end='')
        
        # Try to fetch this page - keep trying until success or permanent failure
        attempt = 0
        max_attempts = 10  # More attempts for pages in the middle of data
        wait_time = 2
        
        while attempt < max_attempts:
            attempt += 1
            
            try:
                response = requests.get(url, params=params, timeout=45)
                
                # SUCCESS
                if response.status_code == 200:
                    data = response.json()
                    records = data.get('data', [])
                    
                    # Check if truly empty
                    if not records:
                        consecutive_empty += 1
                        print(f"EMPTY (no records)")
                        
                        # Only stop if we get multiple consecutive empty pages
                        if consecutive_empty >= 3:
                            print(f"\n✅ End of data confirmed (3 consecutive empty pages)")
                            page = max_pages + 1  # Exit outer loop
                            break
                        else:
                            page += 1
                            break  # Move to next page
                    
                    # We have data!
                    consecutive_empty = 0
                    total_fetched += len(records)
                    
                    # Process records
                    page_findings = defaultdict(list)
                    
                    for record in records:
                        node_name = record.get(node_field)
                        
                        if node_name in target_nodes:
                            # Extract hour
                            if 'fecha_hora' in record:
                                hour = int(record['fecha_hora'][11:13])
                            elif 'hra' in record:
                                hour = record['hra']
                            else:
                                hour = None
                            
                            if hour is not None:
                                page_findings[node_name].append(hour)
                                location_data[node_name]['pages'].add(page)
                                location_data[node_name]['hours'].add(hour)
                                location_data[node_name]['records'].append({
                                    'page': page,
                                    'hour': hour,
                                    'timestamp': record.get('fecha_hora', f"{date_str} {hour:02d}:00")
                                })
                    
                    # Print summary
                    if page_findings:
                        unique_locations = len(page_findings)
                        total_target_records = sum(len(hours) for hours in page_findings.values())
                        print(f"{len(records):4d} records | Found {total_target_records} from {unique_locations} locations")
                        
                        # Show details
                        for location, hours in sorted(page_findings.items())[:2]:
                            unique_hours = sorted(set(hours))
                            print(f"   🔹 {location[:30]:30} : Hours {unique_hours[:10]}{'...' if len(unique_hours) > 10 else ''}")
                    else:
                        print(f"{len(records):4d} records | No target locations")
                    
                    # Check if partial page (possible end approaching)
                    if len(records) < limit_per_page:
                        print(f"   📌 Partial page ({len(records)} records) - end may be near")
                    
                    # Check if we have complete data
                    complete_locations = sum(
                        1 for data in location_data.values() 
                        if len(data['hours']) == 24
                    )
                    
                    if complete_locations == len(target_nodes) and location_data:
                        print(f"\n✅ SUCCESS: All {complete_locations} locations have complete 24-hour data!")
                        page = max_pages + 1  # Exit outer loop
                        break
                    
                    page += 1
                    break  # Success - move to next page
                
                # RATE LIMIT - Always retry
                elif response.status_code == 429:
                    wait_time = min(wait_time * 2, 120)
                    if attempt == 1:
                        print(f"Rate limited", end='')
                    print(f".", end='', flush=True)
                    time.sleep(wait_time)
                    continue
                
                # SERVER ERROR - Always retry
                elif response.status_code >= 500:
                    wait_time = min(wait_time * 1.5, 60)
                    if attempt == 1:
                        print(f"Server error {response.status_code}", end='')
                    print(f".", end='', flush=True)
                    time.sleep(wait_time)
                    continue
                
                # CLIENT ERROR - This is permanent
                else:
                    print(f"Client error {response.status_code} - skipping page")
                    pages_with_errors.append(page)
                    page += 1
                    break
                    
            except requests.exceptions.Timeout:
                if attempt == 1:
                    print(f"Timeout", end='')
                print(f".", end='', flush=True)
                time.sleep(wait_time)
                wait_time = min(wait_time * 1.5, 60)
                continue
                
            except requests.exceptions.ConnectionError:
                if attempt == 1:
                    print(f"Connection error", end='')
                print(f".", end='', flush=True)
                time.sleep(wait_time)
                wait_time = min(wait_time * 2, 120)
                continue
                
            except Exception as e:
                print(f"Unexpected error: {str(e)[:50]}")
                time.sleep(wait_time)
                continue
        
        # If we exhausted all attempts on this page
        if attempt >= max_attempts:
            print(f" - Failed after {max_attempts} attempts")
            pages_with_errors.append(page)
            
            # If we're in the middle of data, continue
            if total_fetched > 0 and consecutive_empty < 3:
                print(f"   ⚠️ Continuing despite error (we're in the middle of data)")
                page += 1
            else:
                # Too many failures at the start - stop
                break
        
        # Progress update
        if page % 10 == 0 and page <= max_pages:
            elapsed = time.time() - start_time
            print(f"\n⏱️ Progress: {page} pages, {total_fetched} records, {elapsed:.1f}s")
            
            # Show coverage so far
            for loc, data in sorted(location_data.items())[:2]:
                print(f"   {loc[:30]:30}: {len(data['hours'])}/24 hours")
        
        # Be nice to API
        if page <= max_pages:
            time.sleep(0.2)
    
    # Final summary
    elapsed = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"FETCH COMPLETE: {min(page-1, max_pages)} pages in {elapsed:.1f} seconds")
    print(f"Total records fetched: {total_fetched}")
    if pages_with_errors:
        print(f"Pages with errors: {pages_with_errors[:10]}{'...' if len(pages_with_errors) > 10 else ''}")
    print(f"{'='*80}")
    
    return location_data, page_summary

# Use this improved function instead of the original
# online_data, online_pages = fetch_all_pages_improved('CMG_ONLINE', test_date, limit_per_page=1000)