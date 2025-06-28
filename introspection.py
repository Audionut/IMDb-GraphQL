#!/usr/bin/env python3
"""
GraphQL introspection script to recursively discover all objects
from the IMDb GraphQL API.
"""

import requests
import json
import time
import sys
import os
import argparse
import random
from typing import Set, Dict, Any

# Rate limiting settings
RATE_LIMIT_DELAY = 0.5  # 0.5 seconds between API calls
last_api_call_time = 0
introspected_types: Set[str] = set()  # Track already introspected types to avoid infinite recursion


def rate_limited_request(url: str, **kwargs) -> requests.Response:
    """
    Make a rate-limited HTTP request with 1 second delay between calls
    """
    global last_api_call_time

    # Calculate time since last API call
    current_time = time.time()
    time_since_last_call = current_time - last_api_call_time

    # If less than rate limit delay, wait
    if time_since_last_call < RATE_LIMIT_DELAY:
        sleep_time = RATE_LIMIT_DELAY - time_since_last_call
        print(f"  Rate limiting: waiting {sleep_time:.2f} seconds...")
        time.sleep(sleep_time)

    response = requests.post(url, **kwargs)
    last_api_call_time = time.time()

    return response


detailed_introspection_data = {}
introspection_counter = 0
total_types_to_introspect = 0
current_group_progress = {"current": 0, "total": 0, "group_name": ""}


def fetch_introspection_data(type_name: str, depth: int = 0, group_info=None) -> Dict[str, Any]:
    """
    Fetch introspection data for a specific GraphQL type
    """
    global introspection_counter, current_group_progress

    # Avoid infinite recursion and duplicate requests
    if type_name in introspected_types:
        print(f"{'  ' * depth}Type '{type_name}' already introspected, skipping...")
        return {}

    # Skip built-in GraphQL types
    if type_name.startswith('__') or type_name in ['String', 'Int', 'Float', 'Boolean', 'ID']:
        return {}

    introspected_types.add(type_name)
    introspection_counter += 1

    # Update group progress if provided
    progress_info = ""
    if group_info:
        current_group_progress["current"] = group_info.get("current", 0)
        current_group_progress["total"] = group_info.get("total", 0)
        current_group_progress["group_name"] = group_info.get("group_name", "")
        progress_info = f"[{current_group_progress['current']}/{current_group_progress['total']} {current_group_progress['group_name']}] "

    url = "https://api.graphql.imdb.com/"
    query = {
        "query": f"""
        {{
            __type(name: "{type_name}") {{
                name
                description
                kind
                fields {{
                    name
                    description
                    type {{
                        name
                        kind
                        ofType {{
                            name
                            kind
                            ofType {{
                                name
                                kind
                                ofType {{
                                    name
                                    kind
                                }}
                            }}
                        }}
                    }}
                    args {{
                        name
                        description
                        type {{
                            name
                            kind
                            ofType {{
                                name
                                kind
                                ofType {{
                                    name
                                    kind
                                }}
                            }}
                        }}
                        defaultValue
                    }}
                }}
                inputFields {{
                    name
                    description
                    type {{
                        name
                        kind
                        ofType {{
                            name
                            kind
                            ofType {{
                                name
                                kind
                                ofType {{
                                    name
                                    kind
                                }}
                            }}
                        }}
                    }}
                    defaultValue
                }}
            }}
        }}
        """
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        print(f"{'  ' * depth}{progress_info}[{introspection_counter}] Introspecting type: {type_name}")

        response = rate_limited_request(
            url,
            json=query,
            headers=headers,
            timeout=30
        )

        if 200 <= response.status_code < 300:
            data = response.json()
            print(f"{'  ' * depth}Successfully fetched data for {type_name}")

            type_data = data.get('data', {}).get('__type', {})
            if not type_data:
                print(f"{'  ' * depth}No type data found for {type_name}")
                return {}

            fields = type_data.get('fields') or []
            input_fields = type_data.get('inputFields') or []
            all_fields = fields + input_fields

            progress_prefix = f"{progress_info}[{introspection_counter}] " if progress_info else f"[{introspection_counter}] "
            print(f"{'  ' * depth}{progress_prefix}Found {len(fields)} fields and {len(input_fields)} input fields in {type_name}")

            related_types = set()
            argument_types = set()
            processed_fields = []

            # Process each field with field-level progress
            if all_fields:
                for field_idx, field in enumerate(all_fields, 1):
                    field_type = field.get('type', {})
                    args = field.get('args') or []

                    # Show field progress for types with many fields
                    field_progress = ""
                    if len(all_fields) > 20:
                        field_progress = f"[{field_idx}/{len(all_fields)} fields] "

                    # Show arguments if they exist
                    args_str = ""
                    processed_args = []
                    if args:
                        for arg in args:
                            arg_type_str = get_type_string(arg.get('type', {}))
                            processed_args.append({
                                'name': arg['name'],
                                'type': arg_type_str,
                                'description': arg.get('description', ''),
                                'defaultValue': arg.get('defaultValue', '')
                            })

                            # Extract argument types for introspection
                            arg_type_names = extract_type_names(arg.get('type', {}))
                            argument_types.update(arg_type_names)

                        arg_names = [f"{arg['name']}: {arg['type']}" for arg in processed_args]
                        args_str = f"({', '.join(arg_names)})"

                    type_str = get_type_string(field_type)
                    print(f"{'  ' * depth}  {field_progress}- {field['name']}{args_str}: {type_str}")

                    # Store processed field information
                    processed_fields.append({
                        'name': field['name'],
                        'type': type_str,
                        'description': field.get('description', ''),
                        'args': processed_args
                    })

                    # Extract related type names for recursive introspection
                    related_type_names = extract_type_names(field_type)
                    related_types.update(related_type_names)

            # Combine field return types and argument types
            all_related_types = related_types.union(argument_types)

            # Store detailed type information
            detailed_introspection_data[type_name] = {
                'name': type_name,
                'description': type_data.get('description', ''),
                'kind': type_data.get('kind', ''),
                'depth': depth,
                'fields': processed_fields,
                'related_types': sorted(list(related_types)),
                'argument_types': sorted(list(argument_types)),
                'all_related_types': sorted(list(all_related_types)),
                'field_count': len(all_fields)
            }

            if type_name == 'Query' and argument_types:
                print(f"{'  ' * depth}Query type detected - prioritizing constraint types...")
                constraint_types = [t for t in argument_types if any(kw in t for kw in ['Constraint', 'Search', 'Sort', 'Filter', 'Input'])]
                if constraint_types:
                    print(f"{'  ' * depth}Found {len(constraint_types)} constraint types to introspect:")
                    for ct in sorted(constraint_types):
                        print(f"{'  ' * depth}   - {ct}")

                    # Introspect constraint types immediately with progress tracking
                    print(f"{'  ' * depth}Starting constraint type introspection...")
                    for i, constraint_type in enumerate(sorted(constraint_types), 1):
                        if constraint_type not in introspected_types:
                            constraint_group_info = {
                                "current": i,
                                "total": len(constraint_types),
                                "group_name": "constraint types"
                            }
                            print(f"{'  ' * depth}Introspecting constraint type: {constraint_type}")
                            fetch_introspection_data(constraint_type, depth + 1, constraint_group_info)

            # Show what types we're going to introspect next
            if all_related_types and depth < 5:
                remaining_types = [t for t in all_related_types if t not in introspected_types]
                if remaining_types:
                    print(f"{'  ' * depth}Will introspect remaining types: {sorted(remaining_types)[:10]}...")
                    if len(remaining_types) > 10:
                        print(f"{'  ' * depth}   ... and {len(remaining_types) - 10} more")

            if depth < 5:
                important_types = []
                constraint_types = []
                connection_types = []
                other_types = []

                # Categorize remaining types
                for related_type in sorted(all_related_types):
                    if related_type in introspected_types:
                        continue
                    elif any(keyword in related_type for keyword in ['Constraint', 'Search', 'Sort', 'Filter', 'Input']):
                        constraint_types.append(related_type)
                    elif related_type in ['Name', 'Title', 'NameText', 'TitleText']:
                        important_types.append(related_type)
                    elif 'Connection' in related_type:
                        connection_types.append(related_type)
                    else:
                        other_types.append(related_type)

                # Introspect in priority order with progress tracking
                priority_order = constraint_types + important_types + connection_types[:3] + other_types[:2]

                if priority_order:
                    print(f"{'  ' * depth}Processing {len(priority_order)} related types...")
                    for i, related_type in enumerate(priority_order, 1):
                        if related_type and related_type not in introspected_types:
                            related_group_info = {
                                "current": i,
                                "total": len(priority_order),
                                "group_name": f"related types (depth {depth})"
                            }
                            print(f"{'  ' * depth}Drilling into: {related_type}")
                            fetch_introspection_data(related_type, depth + 1, related_group_info)

            return type_data

        else:
            print(f"{'  ' * depth}Failed to fetch introspection data for {type_name}: HTTP {response.status_code}")
            print(f"{'  ' * depth}   Response: {response.text[:200]}")
            return {}

    except Exception as e:
        print(f"{'  ' * depth}Request error for {type_name}: {e}")
        import traceback
        print(f"{'  ' * depth}Traceback: {traceback.format_exc()}")
        return {}


def get_type_string(field_type: Dict[str, Any]) -> str:
    """
    Get a readable string representation of a GraphQL type
    """
    if not field_type:
        return "Unknown"

    kind = field_type.get('kind', '')
    name = field_type.get('name', '')
    of_type = field_type.get('ofType', {})

    if kind == 'NON_NULL':
        return f"{get_type_string(of_type)}!"
    elif kind == 'LIST':
        return f"[{get_type_string(of_type)}]"
    elif name:
        return name
    elif of_type:
        return get_type_string(of_type)
    else:
        return f"{kind}(?)"


def extract_type_names(field_type: Dict[str, Any]) -> Set[str]:
    """
    Recursively extract all type names from a field type definition
    """
    type_names = set()

    if not field_type:
        return type_names

    name = field_type.get('name', '')
    kind = field_type.get('kind', '')
    of_type = field_type.get('ofType', {})

    # Add the current type name if it's an object, input, or enum type
    # (Input types are used for arguments, Enums for constraint values)
    if name and kind in ['OBJECT', 'INPUT_OBJECT', 'ENUM', 'INTERFACE', 'UNION']:
        type_names.add(name)

    # Recursively extract from ofType
    if of_type:
        type_names.update(extract_type_names(of_type))

    return type_names


def save_detailed_results():
    """
    Save detailed introspection results preserving hierarchical structure
    """
    print("\nIntrospection Summary:")
    print(f"   Total types introspected: {len(introspected_types)}")

    # Group types by category for better organization
    query_types = []
    object_types = []
    connection_types = []
    other_types = []

    for type_name in sorted(introspected_types):
        if type_name == 'Query':
            query_types.append(type_name)
        elif 'Connection' in type_name:
            connection_types.append(type_name)
        elif type_name[0].isupper():
            object_types.append(type_name)
        else:
            other_types.append(type_name)

    print(f"   Query types: {query_types}")
    print(f"   Object types ({len(object_types)}): {object_types[:10]}{'...' if len(object_types) > 10 else ''}")
    print(f"   Connection types ({len(connection_types)}): {connection_types[:5]}{'...' if len(connection_types) > 5 else ''}")
    print(f"   Other types ({len(other_types)}): {other_types}")

    results = {
        'summary': {
            'total_count': len(introspected_types),
            'query_types': query_types,
            'object_types': object_types,
            'connection_types': connection_types,
            'other_types': other_types,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        },
        'detailed_types': detailed_introspection_data,
        'flat_type_list': sorted(list(introspected_types))
    }

    try:

        print("   Writing comprehensive results...")
        with open('comprehensive_introspection_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        print("Comprehensive results saved to 'comprehensive_introspection_results.json'")

        print("   Writing readable results...")
        readable_results = {}
        for type_name, type_data in detailed_introspection_data.items():
            readable_results[type_name] = {
                'description': type_data.get('description', ''),
                'kind': type_data.get('kind', ''),
                'depth': type_data.get('depth', 0),
                'field_count': type_data.get('field_count', 0),
                'fields': {field['name']: field['type'] for field in type_data.get('fields', [])},
                'related_types': type_data.get('related_types', [])
            }

        with open('readable_introspection_results.json', 'w') as f:
            json.dump(readable_results, f, indent=2)
        print("Readable results saved to 'readable_introspection_results.json'")

    except Exception as e:
        print(f"Could not save detailed results: {e}")
        import traceback
        print(f"Error details: {traceback.format_exc()}")


def categorize_types_consistently(introspected_data):
    """
    Consistently categorize types using both kind and name patterns
    """
    query_types = []
    object_types = []
    connection_types = []
    input_types = []
    enum_types = []
    other_types = []

    for type_name, type_data in introspected_data.items():
        if isinstance(type_data, dict):
            kind = type_data.get('kind', 'Unknown')

            # Primary categorization by GraphQL kind
            if type_name == 'Query':
                query_types.append(type_name)
            elif 'Connection' in type_name:
                connection_types.append(type_name)
            elif kind == 'OBJECT':
                object_types.append(type_name)
            elif kind == 'INPUT_OBJECT':
                input_types.append(type_name)
            elif kind == 'ENUM':
                enum_types.append(type_name)
            elif kind in ['UNION', 'INTERFACE', 'SCALAR']:
                other_types.append(type_name)
            else:
                # Fallback to name-based categorization
                if type_name[0].isupper():
                    object_types.append(type_name)
                else:
                    other_types.append(type_name)

    return {
        'query_types': query_types,
        'object_types': object_types,
        'connection_types': connection_types,
        'input_types': input_types,
        'enum_types': enum_types,
        'other_types': other_types
    }


def generate_markdown_report():
    """
    Generate a concise markdown report with consistent categorization
    """
    try:
        # Get consistent categorization
        categories = categorize_types_consistently(detailed_introspection_data)

        with open('introspection_report.md', 'w', encoding='utf-8') as f:
            f.write("# GraphQL API Introspection Report\n\n")
            f.write(f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Total types discovered: {len(introspected_types)}\n\n")
            f.write("## Summary Statistics\n\n")
            f.write(f"- **Total Types:** {len(introspected_types)}\n")

            total_fields = sum(data.get('field_count', 0) for data in detailed_introspection_data.values() if isinstance(data, dict))
            f.write(f"- **Total Fields:** {total_fields}\n")

            avg_fields = total_fields / len(detailed_introspection_data) if detailed_introspection_data else 0
            f.write(f"- **Average Fields per Type:** {avg_fields:.1f}\n\n")
            f.write("## Type Categories\n\n")
            f.write(f"- **Query Types:** {len(categories['query_types'])}\n")
            f.write(f"- **Object Types:** {len(categories['object_types'])}\n")
            f.write(f"- **Connection Types:** {len(categories['connection_types'])}\n")
            f.write(f"- **Input Types:** {len(categories['input_types'])}\n")
            f.write(f"- **Enum Types:** {len(categories['enum_types'])}\n")
            f.write(f"- **Other Types:** {len(categories['other_types'])}\n\n")

            # Show detailed breakdown
            f.write("## Detailed Type Breakdown\n\n")

            # Kind-based breakdown (from GraphQL introspection)
            kind_counts = {}
            for type_data in detailed_introspection_data.values():
                if isinstance(type_data, dict):
                    kind = type_data.get('kind', 'Unknown')
                    kind_counts[kind] = kind_counts.get(kind, 0) + 1

            f.write("### By GraphQL Kind\n")
            for kind, count in sorted(kind_counts.items()):
                f.write(f"- **{kind}:** {count}\n")
            f.write("\n")

            # Name-based breakdown (for connections, etc.)
            f.write("### By Name Patterns\n")
            f.write(f"- **Query Types:** {len(categories['query_types'])}\n")
            f.write(f"- **Connection Types:** {len(categories['connection_types'])}\n")
            f.write(f"- **Edge Types:** {len([t for t in introspected_types if 'Edge' in t])}\n")
            f.write(f"- **Constraint Types:** {len([t for t in introspected_types if any(kw in t for kw in ['Constraint', 'Search', 'Sort', 'Filter'])])}\n")
            f.write(f"- **Text Types:** {len([t for t in introspected_types if 'Text' in t])}\n\n")

            # Key types of interest
            f.write("## Key Types Found\n\n")
            key_types = ['Query', 'Title', 'Name', 'TitleText', 'NameText', 'TitleConnection', 'NameConnection']
            for type_name in key_types:
                if type_name in detailed_introspection_data:
                    type_data = detailed_introspection_data[type_name]
                    if isinstance(type_data, dict):
                        field_count = type_data.get('field_count', 0)
                        depth = type_data.get('depth', 0)
                        kind = type_data.get('kind', 'Unknown')
                        f.write(f"- **{type_name}**: {field_count} fields (depth {depth}, {kind})\n")
            f.write("\n")

            # Query fields (most important - limit to key ones)
            if 'Query' in detailed_introspection_data:
                f.write("## Key Query Operations\n\n")
                query_data = detailed_introspection_data['Query']
                if isinstance(query_data, dict):
                    query_fields = query_data.get('fields', [])

                    # Group query fields by category and limit each category
                    title_queries = [f for f in query_fields if 'title' in f['name'].lower()][:15]
                    name_queries = [f for f in query_fields if 'name' in f['name'].lower()][:15]
                    search_queries = [f for f in query_fields if 'search' in f['name'].lower()][:10]

                    if title_queries:
                        f.write("### Title-related Queries (Top 15)\n")
                        for field in title_queries:
                            args_summary = f" ({len(field.get('args', []))} args)" if field.get('args') else ""
                            f.write(f"- `{field['name']}{args_summary}`: {field['type']}\n")
                        f.write("\n")

                    if name_queries:
                        f.write("### Name-related Queries (Top 15)\n")
                        for field in name_queries:
                            args_summary = f" ({len(field.get('args', []))} args)" if field.get('args') else ""
                            f.write(f"- `{field['name']}{args_summary}`: {field['type']}\n")
                        f.write("\n")

                    if search_queries:
                        f.write("### Search Queries (Top 10)\n")
                        for field in search_queries:
                            args_summary = f" ({len(field.get('args', []))} args)" if field.get('args') else ""
                            f.write(f"- `{field['name']}{args_summary}`: {field['type']}\n")
                        f.write("\n")

            # Most common field names across all types
            field_frequency = {}
            for type_data in detailed_introspection_data.values():
                if isinstance(type_data, dict):
                    for field in type_data.get('fields', []):
                        field_name = field['name']
                        if field_name not in field_frequency:
                            field_frequency[field_name] = 0
                        field_frequency[field_name] += 1

            most_common = sorted(field_frequency.items(), key=lambda x: x[1], reverse=True)[:20]

            f.write("## Most Common Field Names (Top 20)\n\n")
            f.write("| Field Name | Used in # Types |\n")
            f.write("|------------|----------------|\n")
            for field_name, count in most_common:
                f.write(f"| {field_name} | {count} |\n")
            f.write("\n")

            # Sample of object types with field counts
            f.write("## Sample Object Types\n\n")
            f.write("| Type Name | Fields | Depth | Kind |\n")
            f.write("|-----------|--------|-------|------|\n")

            # Show top 30 object types by field count
            sorted_types = []
            for name, data in detailed_introspection_data.items():
                if name != 'Query' and isinstance(data, dict):
                    sorted_types.append((name, data))

            sorted_types.sort(key=lambda x: x[1].get('field_count', 0), reverse=True)

            for type_name, type_data in sorted_types[:30]:
                field_count = type_data.get('field_count', 0)
                depth = type_data.get('depth', 0)
                kind = type_data.get('kind', 'Unknown')
                f.write(f"| {type_name} | {field_count} | {depth} | {kind} |\n")
            f.write("\n")

            # Constraint types summary
            constraint_types = [t for t in introspected_types if any(kw in t for kw in ['Constraint', 'Search', 'Sort', 'Filter']) and 'INPUT_OBJECT' == detailed_introspection_data.get(t, {}).get('kind')]

            if constraint_types:
                f.write("## Available Constraint Types\n\n")
                f.write("These input types can be used to filter and constrain search queries:\n\n")
                f.write("| Constraint Type | Fields | Description |\n")
                f.write("|-----------------|--------|-------------|\n")

                for constraint_type in sorted(constraint_types)[:15]:
                    if constraint_type in detailed_introspection_data:
                        type_data = detailed_introspection_data[constraint_type]
                        if isinstance(type_data, dict):
                            field_count = type_data.get('field_count', 0)
                            description = type_data.get('description', '')[:50] + ('...' if len(type_data.get('description', '')) > 50 else '')
                            f.write(f"| {constraint_type} | {field_count} | {description} |\n")
                f.write("\n")

            # File structure explanation
            f.write("## Generated Files\n\n")
            f.write("This introspection generated the following files:\n\n")
            f.write("- `comprehensive_introspection_results.json`: Complete detailed results\n")
            f.write("- `readable_introspection_results.json`: Simplified field mappings\n")
            f.write("- `introspection_report.md`: This human-readable summary\n")
            f.write("- `dynamic_query_examples.md`: Working GraphQL query examples\n\n")

            f.write("## Usage Notes\n\n")
            f.write("- The JSON files contain complete type definitions with all fields\n")
            f.write("- Field types ending with `!` are non-nullable (required)\n")
            f.write("- Field types in `[]` are lists/arrays\n")
            f.write("- Connection types typically provide paginated access to collections\n")
            f.write("- Input types (constraints) are used to filter queries\n")
            f.write("- Use the Query type fields as entry points for GraphQL queries\n\n")

        print("Markdown report saved to 'introspection_report.md'")

    except Exception as e:
        print(f"Could not generate markdown report: {e}")
        import traceback
        print(f"Error details: {traceback.format_exc()}")


def generate_example_query_for_type(type_name, entity_id, max_fields=5):
    """Generate an example query for a specific type with a given ID"""
    if type_name not in detailed_introspection_data:
        print(f"Type '{type_name}' not found in introspection data")
        return None

    type_data = detailed_introspection_data[type_name]
    fields = type_data.get('fields', [])

    if not fields:
        print(f"No fields found for type '{type_name}'")
        return None

    # Filter out fields that might be complex or require special handling
    simple_fields = []
    connection_fields = []

    for field in fields:
        field_name = field.get('name', '')
        field_type = field.get('type', '')
        args = field.get('args', [])

        # Categorize fields
        if 'Connection' in field_type:
            connection_fields.append(field)
        elif not args or len(args) == 0:  # Simple fields without arguments
            simple_fields.append(field)

    # Select fields to include in the query
    selected_fields = []

    # Always include 'id' if available
    id_field = next((f for f in simple_fields if f.get('name') == 'id'), None)
    if id_field:
        selected_fields.append(id_field)
        simple_fields.remove(id_field)

    # Add a few more simple fields (prioritize important ones)
    priority_fields = []
    regular_fields = []

    for field in simple_fields:
        field_name = field.get('name', '').lower()
        if any(keyword in field_name for keyword in ['name', 'title', 'text', 'year', 'date', 'url']):
            priority_fields.append(field)
        else:
            regular_fields.append(field)

    # Add priority fields first
    remaining_slots = max_fields - len(selected_fields)
    priority_count = min(remaining_slots - 1, len(priority_fields))
    if priority_count > 0:
        selected_fields.extend(random.sample(priority_fields, priority_count))

    # Add regular fields if we have room
    remaining_slots = max_fields - len(selected_fields)
    if remaining_slots > 1 and regular_fields:
        regular_count = min(remaining_slots - 1, len(regular_fields))
        selected_fields.extend(random.sample(regular_fields, regular_count))

    # Add one connection field if we have room
    if len(selected_fields) < max_fields and connection_fields:
        selected_fields.append(random.choice(connection_fields))

    # Build the query using our dynamic query body builder
    query_body_parts = []

    for field in selected_fields:
        field_name = field.get('name')
        field_type = field.get('type')

        if 'Connection' in field_type:
            # Use our connection query builder
            connection_body = build_connection_query(field_type, depth=1, visited_types={type_name})
            query_body_parts.append(f"    {field_name} {connection_body}")
        else:
            # For non-connection fields, check if they need sub-selection
            if is_scalar_type(field_type):
                query_body_parts.append(f"    {field_name}")
            else:
                # Use our dynamic query body builder for complex types
                sub_body = build_query_body(field_type, depth=1, visited_types={type_name})
                if sub_body and sub_body != "{ id }":
                    query_body_parts.append(f"    {field_name} {sub_body}")
                else:
                    query_body_parts.append(f"    {field_name}")

    # Build the complete query
    query_parts = [f"query Get{type_name} {{"]

    # Find the appropriate Query field for this type
    query_field = find_query_field_for_type(type_name)
    if query_field:
        query_parts.append(f"  {query_field}(id: \"{entity_id}\") {{")
    else:
        # Fallback to lowercase type name
        query_parts.append(f"  {type_name.lower()}(id: \"{entity_id}\") {{")

    query_parts.extend(query_body_parts)
    query_parts.append("  }")
    query_parts.append("}")

    return "\n".join(query_parts)


def find_query_field_for_type(type_name):
    """Find the appropriate Query field that returns the given type"""
    if 'Query' not in detailed_introspection_data:
        return None

    query_data = detailed_introspection_data['Query']
    query_fields = query_data.get('fields', [])

    # Look for fields that return this type
    for field in query_fields:
        field_type = field.get('type', '')
        clean_type = field_type.replace('!', '').replace('[', '').replace(']', '').strip()

        if clean_type == type_name:
            # Check if it has an 'id' argument
            args = field.get('args', [])
            if any(arg.get('name') == 'id' for arg in args):
                return field.get('name')

    # Fallback: look for field with similar name
    type_lower = type_name.lower()
    for field in query_fields:
        field_name = field.get('name', '').lower()
        if field_name == type_lower or field_name == type_lower + 's':
            args = field.get('args', [])
            if any(arg.get('name') == 'id' for arg in args):
                return field.get('name')

    return None


def generate_example_query_for_operation(operation_name, search_term):
    """Generate an example query for a Query operation like advancedNameSearch"""
    if 'Query' not in detailed_introspection_data:
        print("Query type not found in introspection data")
        return None

    query_data = detailed_introspection_data['Query']
    query_fields = query_data.get('fields', [])

    # Find the operation in Query fields
    operation_field = None
    for field in query_fields:
        if field.get('name') == operation_name:
            operation_field = field
            break

    if not operation_field:
        print(f"Operation '{operation_name}' not found in Query type")
        return None

    # Get operation details
    return_type = operation_field.get('type', '')
    args = operation_field.get('args', [])
    description = operation_field.get('description', '')

    print(f"Found operation: {operation_name}")
    print(f"   Returns: {return_type}")
    print(f"   Arguments: {len(args)}")
    if description:
        clean_desc = description.split('\n')[0].strip()
        print(f"   Description: {clean_desc}")

    # Build the query dynamically
    query_args = []
    variables = {}
    constraint_details = {}

    # Process arguments to build the query
    for arg in args:
        arg_name = arg.get('name', '')
        arg_type = arg.get('type', '')
        arg_desc = arg.get('description', '')

        if 'constraint' in arg_name.lower():
            # This is a constraint argument - build example constraints
            constraint_type = arg_type.replace('!', '').strip()
            query_args.append(f"{arg_name}: $constraints")

            # Build example constraints based on the constraint type
            example_constraints = build_example_constraints_for_search(constraint_type, search_term, operation_name)
            variables['constraints'] = example_constraints
            constraint_details[arg_name] = {
                'type': constraint_type,
                'description': arg_desc,
                'example': example_constraints
            }

        elif arg_name in ['first', 'limit']:
            query_args.append(f"{arg_name}: $first")
            variables['first'] = 10

        elif arg_name in ['after', 'before']:
            query_args.append(f"{arg_name}: $after")
            variables['after'] = None

        elif 'sort' in arg_name.lower():
            sort_type = arg_type.replace('!', '').strip()
            query_args.append(f"{arg_name}: $sort")
            variables['sort'] = build_example_sort(sort_type, operation_name)

    # Build the query body using our dynamic builder
    query_body = build_query_body(return_type, depth=0, visited_types=set())

    # Create variable definitions
    var_definitions = []
    if 'constraints' in variables:
        constraint_arg = next(arg for arg in args if 'constraint' in arg.get('name', '').lower())
        constraint_type = constraint_arg.get('type', '').replace('!', '').strip()
        var_definitions.append(f"$constraints: {constraint_type}")
    if 'first' in variables:
        var_definitions.append("$first: Int")
    if 'after' in variables:
        var_definitions.append("$after: ID")
    if 'sort' in variables:
        sort_arg = next((arg for arg in args if 'sort' in arg.get('name', '').lower()), None)
        if sort_arg:
            sort_type = sort_arg.get('type', '').replace('!', '').strip()
            var_definitions.append(f"$sort: {sort_type}")

    # Build the complete query
    args_string = f"({', '.join(query_args)})" if query_args else ""
    var_def_string = f"({', '.join(var_definitions)})" if var_definitions else ""

    query = f"""query {operation_name.capitalize()}Example{var_def_string} {{
  {operation_name}{args_string} {query_body}
}}"""

    return {
        'query': query,
        'variables': variables,
        'constraint_details': constraint_details,
        'operation_info': {
            'name': operation_name,
            'return_type': return_type,
            'description': description,
            'args': args
        }
    }


def build_example_constraints_for_search(constraint_type, search_term, operation_name):
    """Build example constraints based on the constraint type and search term"""
    if constraint_type not in detailed_introspection_data:
        # Fallback constraint
        if 'name' in operation_name.lower():
            return {
                "nameTextConstraint": {
                    "searchTerm": search_term
                }
            }
        elif 'title' in operation_name.lower():
            return {
                "titleTextConstraint": {
                    "searchTerm": search_term
                }
            }
        else:
            return {"searchTerm": search_term}

    constraint_data = detailed_introspection_data[constraint_type]
    constraint_fields = constraint_data.get('fields', [])

    example_constraints = {}

    # Analyze constraint fields and build appropriate example
    for field in constraint_fields:
        field_name = field.get('name', '')
        field_name_lower = field_name.lower()

        # Primary search term constraint
        if any(keyword in field_name_lower for keyword in ['nametext', 'titletext', 'text', 'search']):
            if 'name' in field_name_lower:
                example_constraints['nameTextConstraint'] = {
                    "searchTerm": search_term
                }
            elif 'title' in field_name_lower:
                example_constraints['titleTextConstraint'] = {
                    "searchTerm": search_term
                }
            else:
                example_constraints[field_name] = {
                    "searchTerm": search_term
                }

        # Additional useful constraints for demonstration
        elif 'profession' in field_name_lower and len(example_constraints) < 3:
            example_constraints[field_name] = {
                "anyProfessions": ["ACTOR", "PRODUCER"]
            }

        elif 'birthdate' in field_name_lower and len(example_constraints) < 3:
            example_constraints[field_name] = {
                "start": "1960-01-01",
                "end": "1970-12-31"
            }

        elif 'year' in field_name_lower and len(example_constraints) < 3:
            example_constraints[field_name] = {
                "start": 1990,
                "end": 2000
            }

        elif 'gender' in field_name_lower and len(example_constraints) < 3:
            example_constraints[field_name] = "MALE"

    # Ensure we have at least one constraint
    if not example_constraints:
        if 'name' in operation_name.lower():
            example_constraints['nameTextConstraint'] = {
                "searchTerm": search_term
            }
        elif 'title' in operation_name.lower():
            example_constraints['titleTextConstraint'] = {
                "searchTerm": search_term
            }

    return example_constraints


def build_example_sort(sort_type, operation_name):
    """Build an example sort object"""
    if sort_type not in detailed_introspection_data:
        return {
            "sortBy": "RELEVANCE",
            "sortOrder": "DESC"
        }

    sort_data = detailed_introspection_data[sort_type]
    sort_fields = sort_data.get('fields', [])

    example_sort = {}

    for field in sort_fields:
        field_name = field.get('name', '')

        if 'sortby' in field_name.lower() or 'sort_by' in field_name.lower():
            if 'name' in operation_name.lower():
                example_sort[field_name] = "POPULARITY"
            elif 'title' in operation_name.lower():
                example_sort[field_name] = "USER_RATING"
            else:
                example_sort[field_name] = "RELEVANCE"

        elif 'order' in field_name.lower():
            example_sort[field_name] = "DESC"

    return example_sort if example_sort else {"sortBy": "RELEVANCE", "sortOrder": "DESC"}


def generate_query_examples(args=None):
    """Generate example GraphQL queries using dynamic query building"""

    # If specific example requested
    if args and args.example:
        type_or_operation, identifier = args.example

        # Check if it's a Query operation first
        if 'Query' in detailed_introspection_data:
            query_fields = detailed_introspection_data['Query'].get('fields', [])
            operation_names = [f.get('name') for f in query_fields]

            if type_or_operation in operation_names:
                # It's a Query operation
                print(f"Generating example query for operation: {type_or_operation}")
                print(f"   Search term: {identifier}")
                print("=" * 80)

                result = generate_example_query_for_operation(type_or_operation, identifier)
                if result:
                    print(result['query'])
                    print("=" * 80)
                    print(f"Example query generated for operation: {type_or_operation}")

                    try:
                        safe_identifier = str(identifier).replace(' ', '_').replace(':', '_').replace('"', '').replace("'", '')
                        filename = f"example_{type_or_operation}_{safe_identifier}.md"

                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(f"# Example Query for {type_or_operation}\n\n")
                            f.write(f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                            f.write(f"**Operation:** {type_or_operation}  \n")
                            f.write(f"**Search Term:** {identifier}  \n")
                            f.write(f"**Returns:** {result['operation_info']['return_type']}  \n\n")

                            if result['operation_info']['description']:
                                clean_desc = result['operation_info']['description'].split('\n')[0].strip()
                                f.write(f"**Description:** {clean_desc}\n\n")

                            f.write("## Generated Query\n\n")
                            f.write("```graphql\n")
                            f.write(result['query'])
                            f.write("\n```\n\n")

                            # Show variables
                            if result['variables']:
                                f.write("## Variables\n\n")
                                f.write("```json\n")
                                f.write(json.dumps(result['variables'], indent=2))
                                f.write("\n```\n\n")

                            # Show constraint details
                            if result['constraint_details']:
                                f.write("## Available Constraint Types\n\n")
                                for constraint_name, constraint_info in result['constraint_details'].items():
                                    constraint_type = constraint_info['type']
                                    f.write(f"### {constraint_name} ({constraint_type})\n\n")

                                    if constraint_info['description']:
                                        clean_desc = constraint_info['description'].split('\n')[0].strip()
                                        f.write(f"{clean_desc}\n\n")

                                    # Show all available constraint fields
                                    if constraint_type in detailed_introspection_data:
                                        constraint_data = detailed_introspection_data[constraint_type]
                                        constraint_fields = constraint_data.get('fields', [])

                                        f.write("**Available constraint fields:**\n\n")
                                        f.write("| Field Name | Type | Description |\n")
                                        f.write("|------------|------|-------------|\n")

                                        for field in constraint_fields:
                                            field_name = field.get('name', 'Unknown')
                                            field_type = field.get('type', 'Unknown')
                                            field_desc = field.get('description', 'No description')

                                            # Clean description - handle None values
                                            if field_desc and '\n' in field_desc:
                                                field_desc = field_desc.split('\n')[0].strip()
                                            if field_desc and len(field_desc) > 60:
                                                field_desc = field_desc[:60] + "..."

                                            # Ensure field_desc is not None before replace
                                            if field_desc:
                                                field_desc = field_desc.replace('|', '\\|')
                                            else:
                                                field_desc = 'No description'

                                            f.write(f"| {field_name} | {field_type} | {field_desc} |\n")
                                        f.write("\n")

                                    f.write("**Example usage:**\n")
                                    f.write("```json\n")
                                    f.write(json.dumps(constraint_info['example'], indent=2))
                                    f.write("\n```\n\n")

                            # Show operation arguments
                            f.write("## Operation Arguments\n\n")
                            f.write("| Argument | Type | Description |\n")
                            f.write("|----------|------|-------------|\n")

                            for arg in result['operation_info']['args']:
                                arg_name = arg.get('name', 'Unknown')
                                arg_type = arg.get('type', 'Unknown')
                                arg_desc = arg.get('description', 'No description')

                                if arg_desc and '\n' in arg_desc:
                                    arg_desc = arg_desc.split('\n')[0].strip()
                                if arg_desc and len(arg_desc) > 60:
                                    arg_desc = arg_desc[:60] + "..."
                                if arg_desc:
                                    arg_desc = arg_desc.replace('|', '\\|')
                                else:
                                    arg_desc = 'No description'

                                f.write(f"| {arg_name} | {arg_type} | {arg_desc} |\n")
                            f.write("\n")

                            # Usage tips
                            f.write("## Usage Tips\n\n")
                            f.write("- Modify the constraint values to match your search criteria\n")
                            f.write("- Use `first` parameter to control the number of results\n")
                            f.write("- Add `after` cursor for pagination\n")
                            f.write("- Combine multiple constraints for more specific searches\n")
                            f.write("- Check the constraint field tables above for all available options\n\n")

                        print(f"Example saved to '{filename}'")

                    except Exception as e:
                        print(f"Could not save example: {e}")
                        import traceback
                        print(f"Error details: {traceback.format_exc()}")

                    # Show constraint summary in console
                    if result['constraint_details']:
                        print("\nAvailable Constraint Types:")
                        for constraint_name, constraint_info in result['constraint_details'].items():
                            constraint_type = constraint_info['type']
                            if constraint_type in detailed_introspection_data:
                                field_count = detailed_introspection_data[constraint_type].get('field_count', 0)
                                print(f"  • {constraint_name}: {constraint_type} ({field_count} fields)")
                            else:
                                print(f"  • {constraint_name}: {constraint_type}")

                        print("\nSee generated markdown file for complete constraint field listings")

                return

        # If not a Query operation, try as a type (existing functionality)
        type_name, entity_id = type_or_operation, identifier
        print(f"Generating example query for {type_name} with ID: {entity_id}")
        print("=" * 80)

        query = generate_example_query_for_type(type_name, entity_id)
        if query:
            print(query)
            print("=" * 80)
            print(f"Example query generated for {type_name}")

            try:
                safe_entity_id = str(entity_id).replace(':', '_').replace(' ', '_')
                filename = f"example_{type_name.lower()}_{safe_entity_id}.md"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"# Example Query for {type_name}\n\n")
                    f.write(f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    f.write(f"**Type:** {type_name}  \n")
                    f.write(f"**Entity ID:** {entity_id}  \n\n")
                    f.write("## Generated Query\n\n")
                    f.write("```graphql\n")
                    f.write(query)
                    f.write("\n```\n\n")

                    # Add field information - SHOW ALL FIELDS
                    if type_name in detailed_introspection_data:
                        type_data = detailed_introspection_data[type_name]
                        f.write(f"## Available Fields in {type_name}\n\n")
                        f.write(f"The {type_name} type has {type_data.get('field_count', 0)} total fields.\n\n")

                        fields = type_data.get('fields', [])

                        # Categorize fields for better documentation
                        scalar_fields = []
                        complex_fields = []
                        connection_fields = []

                        for field in fields:
                            field_type = field.get('type', '')
                            if 'Connection' in field_type:
                                connection_fields.append(field)
                            elif is_scalar_type(field_type):
                                scalar_fields.append(field)
                            else:
                                complex_fields.append(field)

                        # Document ALL scalar fields
                        if scalar_fields:
                            f.write("### Simple Fields\n\n")
                            f.write("| Field Name | Type | Description |\n")
                            f.write("|------------|------|-------------|\n")
                            for field in scalar_fields:
                                field_name = field.get('name', 'Unknown')
                                field_type = field.get('type', 'Unknown')
                                description = field.get('description', 'No description')

                                # Clean description - only take text before first newline
                                if description and '\n' in description:
                                    description = description.split('\n')[0].strip()

                                # Limit length for table display
                                if description and len(description) > 80:
                                    description = description[:80] + "..."

                                # Escape markdown table characters
                                description = description.replace('\n', ' ').replace('|', '\\|')
                                f.write(f"| {field_name} | {field_type} | {description} |\n")
                            f.write("\n")

                        # Document ALL complex fields
                        if complex_fields:
                            f.write("### Complex Object Fields\n\n")
                            f.write("| Field Name | Type | Description |\n")
                            f.write("|------------|------|-------------|\n")
                            for field in complex_fields:
                                field_name = field.get('name', 'Unknown')
                                field_type = field.get('type', 'Unknown')
                                description = field.get('description', 'No description')

                                # Clean description - only take text before first newline
                                if description and '\n' in description:
                                    description = description.split('\n')[0].strip()

                                # Limit length for table display
                                if description and len(description) > 80:
                                    description = description[:80] + "..."

                                # Escape markdown table characters
                                description = description.replace('\n', ' ').replace('|', '\\|')
                                f.write(f"| {field_name} | {field_type} | {description} |\n")
                            f.write("\n")

                        # Document ALL connection fields
                        if connection_fields:
                            f.write("### Connection Fields (Paginated Data)\n\n")
                            f.write("| Field Name | Type | Description |\n")
                            f.write("|------------|------|-------------|\n")
                            for field in connection_fields:
                                field_name = field.get('name', 'Unknown')
                                field_type = field.get('type', 'Unknown')
                                description = field.get('description', 'No description')

                                # Clean description - only take text before first newline
                                if description and '\n' in description:
                                    description = description.split('\n')[0].strip()

                                # Limit length for table display
                                if description and len(description) > 80:
                                    description = description[:80] + "..."

                                # Escape markdown table characters
                                description = description.replace('\n', ' ').replace('|', '\\|')
                                f.write(f"| {field_name} | {field_type} | {description} |\n")
                            f.write("\n")

                        # Add field count summary
                        f.write("### Field Summary\n\n")
                        f.write(f"- **Total Fields:** {len(fields)}\n")
                        f.write(f"- **Simple Fields:** {len(scalar_fields)}\n")
                        f.write(f"- **Complex Object Fields:** {len(complex_fields)}\n")
                        f.write(f"- **Connection Fields:** {len(connection_fields)}\n\n")

                    # Add usage tips
                    f.write("## Usage Tips\n\n")
                    f.write("- This query is dynamically generated based on the introspected schema\n")
                    f.write("- You can add or remove fields based on your data needs\n")
                    f.write("- Connection fields support pagination with `first`, `last`, `after`, `before` arguments\n")
                    f.write("- Replace the ID with actual IMDb IDs for your queries\n")
                    f.write("- Some fields may require additional arguments not shown in this basic example\n\n")

                    # Add related queries suggestion
                    query_field = find_query_field_for_type(type_name)
                    if query_field:
                        f.write("## Related Query Operations\n\n")
                        f.write(f"This example uses the `{query_field}` operation. ")
                        f.write("You might also be interested in:\n\n")

                        # Suggest related operations
                        if 'Query' in detailed_introspection_data:
                            query_fields = detailed_introspection_data['Query'].get('fields', [])
                            related_fields = []

                            for field in query_fields:
                                field_name = field.get('name', '')
                                if (type_name.lower() in field_name.lower() and
                                        field_name != query_field):
                                    related_fields.append(field_name)

                            if related_fields:
                                for related_field in related_fields[:5]:
                                    f.write(f"- `{related_field}`\n")
                            else:
                                f.write("- Search operations like `advancedTitleSearch` or `advancedNameSearch`\n")
                                f.write("- Collection operations like `titles` or `names`\n")

                print(f"Example saved to '{filename}'")

            except Exception as e:
                print(f"Could not save example: {e}")

            # Show field descriptions in console as well
            if type_name in detailed_introspection_data:
                type_data = detailed_introspection_data[type_name]
                total_fields = len(type_data.get('fields', []))
                print(f"\nSample of {min(10, total_fields)} fields from {type_name} (total: {total_fields}):")

                fields = type_data.get('fields', [])
                # Show random selection of 10 fields (or all if less than 10)
                if len(fields) > 10:
                    sample_fields = random.sample(fields, 10)
                else:
                    sample_fields = fields

                for field in sample_fields:
                    field_name = field.get('name', 'Unknown')
                    field_type = field.get('type', 'Unknown')
                    description = field.get('description', 'No description')

                    # Clean description - only take text before first newline
                    if description and '\n' in description:
                        description = description.split('\n')[0].strip()

                    # Truncate for console display
                    if description and len(description) > 100:
                        description = description[:100] + "..."

                    print(f"  • {field_name}: {field_type}")
                    if description and description != 'No description':
                        print(f"    {description}")

                if total_fields > 10:
                    print(f"  ... and {total_fields - 10} more fields (see generated markdown file for complete list)")
        return

    # Generate general examples using dynamic query building
    print("Generating dynamic GraphQL query examples...")
    print("=" * 80)

    examples = []

    # Look for interesting Query fields and generate examples
    if 'Query' in detailed_introspection_data:
        query_fields = detailed_introspection_data['Query'].get('fields', [])

        # Find different types of query fields
        title_queries = [f for f in query_fields if 'title' in f['name'].lower() and f.get('args')]
        name_queries = [f for f in query_fields if 'name' in f['name'].lower() and f.get('args')]
        search_queries = [f for f in query_fields if 'search' in f['name'].lower() and f.get('args')]

        # Generate examples for different categories
        for field in title_queries[:2]:  # 2 title examples
            example = generate_dynamic_example_query(field)
            if example:
                examples.append(example)

        for field in name_queries[:2]:  # 2 name examples
            example = generate_dynamic_example_query(field)
            if example:
                examples.append(example)

        for field in search_queries[:3]:  # 3 search examples
            example = generate_dynamic_example_query(field)
            if example:
                examples.append(example)

    # Display the examples
    for i, example in enumerate(examples, 1):
        print(f"{i}. {example['title']}")
        print(f"   {example['description']}")
        print()
        print(example['query'])
        if example.get('variables'):
            print("\nVariables:")
            print(json.dumps(example['variables'], indent=2))
        print("=" * 80)

    # Save examples to file
    if examples:
        try:
            with open('query_examples.md', 'w', encoding='utf-8') as f:
                f.write("# GraphQL Query Examples\n\n")
                f.write(f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("These examples are dynamically generated from the introspected schema.\n\n")

                for i, example in enumerate(examples, 1):
                    f.write(f"## Example {i}: {example['title']}\n\n")
                    f.write(f"{example['description']}\n\n")
                    f.write("```graphql\n")
                    f.write(example['query'])
                    f.write("\n```\n\n")
                    if example.get('variables'):
                        f.write("**Variables:**\n")
                        f.write("```json\n")
                        f.write(json.dumps(example['variables'], indent=2))
                        f.write("\n```\n\n")
                    f.write("---\n\n")

            print(f"Query examples saved to 'query_examples.md' ({len(examples)} examples)")
        except Exception as e:
            print(f"Could not save examples: {e}")

    print("\nTips for using these queries:")
    print("• Replace the ID values with actual IMDb IDs")
    print("• Adjust the 'first' parameter to control how many results you get")
    print("• Add or remove fields based on what data you need")
    print("• Use the constraint variables to filter your searches")


def clean_description(description):
    """
    Clean description by taking only text before the first newline and handling None values
    """
    if not description:
        return "No description"

    # Split on first newline and take only the first part
    clean_desc = description.split('\n')[0].strip()

    # Return cleaned description or fallback
    return clean_desc if clean_desc else "No description"


def generate_example_query(field_info, constraint_type):
    """
    Generate an example query for a search field with constraints
    """
    try:
        field_name = field_info['name']
        return_type = field_info['type']

        # Get constraint structure
        constraint_data = detailed_introspection_data.get(constraint_type, {})
        constraint_fields = constraint_data.get('fields', [])

        # Build example constraint object
        example_constraints = {}
        variables = {"first": 10}

        # Look for common constraint patterns
        for constraint_field in constraint_fields:
            field_name_lower = constraint_field['name'].lower()

            if 'nametext' in field_name_lower or 'name' in field_name_lower:
                if 'NameTextConstraint' in detailed_introspection_data:
                    example_constraints['nameTextConstraint'] = {
                        'searchTerm': 'SEARCH_TERM_HERE'
                    }
            elif 'titletext' in field_name_lower or 'title' in field_name_lower:
                if 'TitleTextConstraint' in detailed_introspection_data:
                    example_constraints['titleTextConstraint'] = {
                        'searchTerm': 'TITLE_SEARCH_HERE'
                    }
            elif 'birthdate' in field_name_lower:
                example_constraints['birthDateConstraint'] = {
                    'start': '1980-01-01',
                    'end': '1990-12-31'
                }
            elif 'profession' in field_name_lower:
                example_constraints['professionConstraint'] = {
                    'anyProfessions': ['ACTOR', 'DIRECTOR']
                }

        if not example_constraints:
            return None

        variables['constraints'] = example_constraints

        query_body = build_query_body(return_type)

        query = f'''query {field_name.capitalize()}Example($constraints: {constraint_type}, $first: Int!) {{
    {field_name}(
        constraints: $constraints,
        first: $first
    ) {query_body}
}}'''

        return {
            'title': f'{field_name.capitalize()} with Constraints',
            'description': f'Search using {field_name} with various constraint options.',
            'query': query,
            'variables': variables
        }

    except Exception as e:
        print(f"Error generating example for {field_info.get('name', 'unknown')}: {e}")
        return None


def build_enhanced_connection_query(connection_type, depth, visited_types):
    """
    Build an enhanced query for Connection types with richer node content
    """
    indent = "    " * (depth + 1)
    edge_indent = "    " * (depth + 2)
    node_indent = "    " * (depth + 3)

    # Try to determine the node type from the connection name
    node_type = connection_type.replace('Connection', '').replace('Edge', '')

    # Handle special cases for AdvancedNameSearchConnection
    if 'AdvancedNameSearch' in connection_type:
        node_type = 'Name'
    elif 'AdvancedTitleSearch' in connection_type:
        node_type = 'Title'

    # Build enhanced node query with more fields
    node_query_parts = [f"{node_indent}id"]

    if node_type in detailed_introspection_data:
        node_data = detailed_introspection_data[node_type]
        node_fields = node_data.get('fields', [])

        # Add key fields for Name objects
        if node_type == 'Name':
            key_fields = ['nameText', 'primaryImage', 'primaryProfession', 'birthDate', 'deathDate', 'knownFor']
        elif node_type == 'Title':
            key_fields = ['titleText', 'primaryImage', 'releaseYear', 'ratingsSummary', 'titleType', 'runtime']
        else:
            # Generic approach - find important fields
            key_fields = [f['name'] for f in node_fields if any(kw in f['name'].lower()
                          for kw in ['text', 'name', 'title', 'image', 'date', 'year', 'rating'])][:5]

        for field_name in key_fields:
            field = next((f for f in node_fields if f['name'] == field_name), None)
            if field:
                field_type = field['type']
                if is_scalar_type(field_type):
                    node_query_parts.append(f"{node_indent}{field_name}")
                else:
                    # Build sub-query for complex fields with limited depth
                    if field_name == 'knownFor' and 'Connection' in field_type:
                        # Special handling for knownFor connection - limit to basic info
                        node_query_parts.append(f"{node_indent}{field_name}(first: 3) {{")
                        node_query_parts.append(f"{node_indent}    edges {{")
                        node_query_parts.append(f"{node_indent}        node {{")
                        node_query_parts.append(f"{node_indent}            id")
                        node_query_parts.append(f"{node_indent}            titleText {{ text }}")
                        node_query_parts.append(f"{node_indent}            releaseYear {{ year }}")
                        node_query_parts.append(f"{node_indent}        }}")
                        node_query_parts.append(f"{node_indent}    }}")
                        node_query_parts.append(f"{node_indent}}}")
                    else:
                        # Build sub-query for complex fields
                        sub_query = build_query_body(field_type, depth + 4, visited_types)
                        if sub_query and sub_query != "{ id }":
                            node_query_parts.append(f"{node_indent}{field_name} {sub_query}")
                        else:
                            node_query_parts.append(f"{node_indent}{field_name}")

    node_query = "{\n" + "\n".join(node_query_parts) + f"\n{node_indent}    }}"

    connection_query = f"""{{
{indent}edges {{
{edge_indent}node {node_query}
{edge_indent}cursor
{indent}}}
{indent}pageInfo {{
{edge_indent}hasNextPage
{edge_indent}hasPreviousPage
{edge_indent}startCursor
{edge_indent}endCursor
{indent}}}
{indent}total
{'    ' * depth}}}"""

    return connection_query


def build_query_body(return_type, depth=0, visited_types=None):
    """
    Dynamically build a query body by traversing the detailed_introspection_data hierarchy
    Enhanced to build richer queries for operations
    """
    if visited_types is None:
        visited_types = set()

    if depth > 3:  # Prevent infinite recursion
        return "{ id }"

    # Clean up the type name
    clean_type = return_type.replace('!', '').replace('[', '').replace(']', '').strip()

    # Avoid circular references
    if clean_type in visited_types:
        return "{ id }"

    visited_types = visited_types.copy()
    visited_types.add(clean_type)

    # Handle Connection types specially with richer content
    if 'Connection' in clean_type:
        return build_enhanced_connection_query(clean_type, depth, visited_types)

    # Handle Edge types
    if 'Edge' in clean_type:
        return build_edge_query(clean_type, depth, visited_types)

    # Check if we have introspection data for this type
    if clean_type not in detailed_introspection_data:
        return "{ id }"

    type_data = detailed_introspection_data[clean_type]
    fields = type_data.get('fields', [])
    kind = type_data.get('kind', '')

    # Handle different GraphQL kinds
    if kind == 'ENUM':
        return ""

    if kind == 'SCALAR':
        return ""

    # Build field selection intelligently
    selected_fields = []
    indent = "    " * (depth + 1)

    # Always include ID if available
    id_fields = [f for f in fields if f['name'] in ['id', 'ID']]
    for field in id_fields:
        selected_fields.append(f"{indent}{field['name']}")

    # Include simple scalar fields (String, Int, Boolean, etc.)
    scalar_fields = []
    for field in fields:
        field_type = field['type']
        field_name = field['name']

        # Skip if already added
        if field_name in ['id', 'ID'] and id_fields:
            continue

        # Check if it's a simple scalar type
        if is_scalar_type(field_type):
            scalar_fields.append(field)

    # Prioritize important scalar fields
    priority_scalars = []
    regular_scalars = []

    for field in scalar_fields:
        field_name = field['name'].lower()
        if any(keyword in field_name for keyword in ['name', 'title', 'text', 'url', 'date', 'year', 'rating', 'count']):
            priority_scalars.append(field)
        else:
            regular_scalars.append(field)

    # Add priority scalars first
    for field in priority_scalars[:10]:
        selected_fields.append(f"{indent}{field['name']}")

    # Add some regular scalars
    for field in regular_scalars[:7]:
        selected_fields.append(f"{indent}{field['name']}")

    # Include some interesting object/complex fields
    complex_fields = []
    for field in fields:
        field_type = field['type']
        field_name = field['name']

        if not is_scalar_type(field_type) and field_name not in ['id', 'ID']:
            complex_fields.append(field)

    # Prioritize certain complex fields
    priority_complex = []
    regular_complex = []

    for field in complex_fields:
        field_name = field['name'].lower()
        field_type = field['type']

        # High priority complex fields for names
        if any(keyword in field_name for keyword in ['primaryimage', 'nametext', 'primaryprofession', 'birthdate', 'deathdate']):
            priority_complex.append(field)
        # Medium priority - connections we might want to explore
        elif 'Connection' in field_type and any(keyword in field_name for keyword in ['knownfor', 'filmography', 'credit']):
            regular_complex.append(field)
        # Text objects are often useful
        elif 'Text' in field_type:
            priority_complex.append(field)
        # Other objects
        elif field_type in detailed_introspection_data:
            regular_complex.append(field)

    # Add priority complex fields
    for field in priority_complex[:5]:
        field_name = field['name']
        field_type = field['type']

        sub_query = build_query_body(field_type, depth + 1, visited_types)
        if sub_query.strip():
            if sub_query == '""' or sub_query == "":
                selected_fields.append(f"{indent}{field_name}")
            else:
                selected_fields.append(f"{indent}{field_name} {sub_query}")
        else:
            selected_fields.append(f"{indent}{field_name}")

    # Add some regular complex fields if we have room
    if len(selected_fields) < 20:
        for field in regular_complex[:3]:
            field_name = field['name']
            field_type = field['type']

            sub_query = build_query_body(field_type, depth + 1, visited_types)
            if sub_query.strip():
                if sub_query == '""' or sub_query == "":
                    selected_fields.append(f"{indent}{field_name}")
                else:
                    selected_fields.append(f"{indent}{field_name} {sub_query}")
            else:
                selected_fields.append(f"{indent}{field_name}")

    if not selected_fields:
        return "{ id }"

    # Build the query body
    query_body = "{\n" + "\n".join(selected_fields) + f"\n{'    ' * depth}}}"
    return query_body


def build_connection_query(connection_type, depth, visited_types):
    """
    Build a query for Connection types (pagination pattern)
    """
    indent = "    " * (depth + 1)
    edge_indent = "    " * (depth + 2)
    node_indent = "    " * (depth + 3)

    # Try to determine the node type from the connection name
    node_type = connection_type.replace('Connection', '').replace('Edge', '')

    # Build node query
    node_query = "{\n" + node_indent + "id"

    if node_type in detailed_introspection_data:
        node_body = build_query_body(node_type, depth + 3, visited_types)
        if node_body and node_body != "{ id }":
            # Extract the inner content of the node body
            inner_content = node_body.strip()
            if inner_content.startswith('{') and inner_content.endswith('}'):
                inner_content = inner_content[1:-1].strip()
                if inner_content:
                    node_query = "{\n" + inner_content + f"\n{node_indent}}}"
                else:
                    node_query += f"\n{node_indent}}}"
            else:
                node_query += f"\n{node_indent}}}"
        else:
            node_query += f"\n{node_indent}}}"
    else:
        node_query += f"\n{node_indent}}}"

    connection_query = f"""{{
{indent}edges {{
{edge_indent}node {node_query}
{edge_indent}cursor
{indent}}}
{indent}pageInfo {{
{edge_indent}hasNextPage
{edge_indent}hasPreviousPage
{edge_indent}startCursor
{edge_indent}endCursor
{indent}}}
{indent}total
{'    ' * depth}}}"""

    return connection_query


def build_edge_query(edge_type, depth, visited_types):
    """
    Build a query for Edge types
    """
    indent = "    " * (depth + 1)
    node_indent = "    " * (depth + 2)

    # Try to determine the node type from the edge name
    node_type = edge_type.replace('Edge', '')

    edge_query = f"""{{
{indent}node {{
{node_indent}id"""

    if node_type in detailed_introspection_data:
        node_body = build_query_body(node_type, depth + 2, visited_types)
        if node_body and node_body != "{ id }":
            # Extract the inner content
            inner_content = node_body.strip()
            if inner_content.startswith('{') and inner_content.endswith('}'):
                inner_content = inner_content[1:-1].strip()
                if inner_content:
                    edge_query += f"\n{inner_content}"

    edge_query += f"""
{indent}}}
{indent}cursor
{'    ' * depth}}}"""

    return edge_query


def is_scalar_type(field_type):
    """
    Check if a field type is a scalar (leaf) type
    """
    clean_type = field_type.replace('!', '').replace('[', '').replace(']', '').strip()

    # Built-in GraphQL scalars
    if clean_type in ['String', 'Int', 'Float', 'Boolean', 'ID']:
        return True

    # Check if it's an ENUM in our introspection data
    if clean_type in detailed_introspection_data:
        type_data = detailed_introspection_data[clean_type]
        kind = type_data.get('kind', '')
        return kind in ['ENUM', 'SCALAR']

    # Custom scalars (common patterns)
    if any(keyword in clean_type.lower() for keyword in ['date', 'time', 'url', 'uri']):
        return True

    return False


def generate_dynamic_query_examples():
    """
    Generate example GraphQL queries using the dynamic query builder
    """
    try:
        examples = []

        # Look for advanced search operations
        if 'Query' in detailed_introspection_data:
            query_fields = detailed_introspection_data['Query'].get('fields', [])

            # Find interesting query fields
            search_fields = [f for f in query_fields if 'search' in f['name'].lower()]
            title_fields = [f for f in query_fields if 'title' in f['name'].lower() and len(f.get('args', [])) > 0]
            name_fields = [f for f in query_fields if 'name' in f['name'].lower() and len(f.get('args', [])) > 0]

            # Generate examples for search fields
            for field in search_fields[:3]:  # Limit to 3 search examples
                example = generate_dynamic_example_query(field)
                if example:
                    examples.append(example)

            # Generate examples for title fields
            for field in title_fields[:2]:  # Limit to 2 title examples
                example = generate_dynamic_example_query(field)
                if example:
                    examples.append(example)

            # Generate examples for name fields
            for field in name_fields[:2]:  # Limit to 2 name examples
                example = generate_dynamic_example_query(field)
                if example:
                    examples.append(example)

        # Save dynamic query examples
        if examples:
            with open('dynamic_query_examples.md', 'w', encoding='utf-8') as f:
                f.write("# Dynamic GraphQL Query Examples\n\n")
                f.write(f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("These examples are dynamically generated from the introspected schema.\n\n")

                for i, example in enumerate(examples, 1):
                    f.write(f"## Example {i}: {example['title']}\n\n")
                    f.write(f"{example['description']}\n\n")
                    f.write("```graphql\n")
                    f.write(example['query'])
                    f.write("\n```\n\n")
                    if example.get('variables'):
                        f.write("**Variables:**\n")
                        f.write("```json\n")
                        f.write(json.dumps(example['variables'], indent=2))
                        f.write("\n```\n\n")
                    f.write("---\n\n")

            print(f"Dynamic query examples saved to 'dynamic_query_examples.md' ({len(examples)} examples)")

    except Exception as e:
        print(f"Could not generate dynamic query examples: {e}")


def generate_dynamic_example_query(field_info):
    """
    Generate a dynamic example query using the enhanced query builder
    """
    try:
        field_name = field_info['name']
        return_type = field_info['type']
        args = field_info.get('args', [])

        # Build dynamic query body using our enhanced function
        query_body = build_query_body(return_type)

        # Build arguments
        query_args = []
        variables = {}

        # Handle different argument patterns
        for arg in args[:5]:  # Limit to 5 arguments
            arg_name = arg['name']
            arg_type = arg['type']

            if 'first' in arg_name.lower() or 'limit' in arg_name.lower():
                query_args.append(f"{arg_name}: $first")
                variables['first'] = 10
            elif 'constraint' in arg_name.lower():
                query_args.append(f"{arg_name}: $constraints")
                variables['constraints'] = build_example_constraints(arg_type)
            elif 'id' in arg_name.lower():
                query_args.append(f"{arg_name}: $id")
                variables['id'] = "nm0000001"  # Example IMDb ID
            elif 'text' in arg_name.lower() or 'query' in arg_name.lower():
                query_args.append(f"{arg_name}: $searchText")
                variables['searchText'] = "example search"

        # Build the complete query
        args_string = f"({', '.join(query_args)})" if query_args else ""

        query = f'''query {field_name.capitalize()}Example({build_variable_definitions(variables)}) {{
    {field_name}{args_string} {query_body}
}}'''

        return {
            'title': f'{field_name.capitalize()} - Dynamic Query',
            'description': f'Dynamically generated query for {field_name} using introspected schema structure.',
            'query': query,
            'variables': variables if variables else None
        }

    except Exception as e:
        print(f"Error generating dynamic example for {field_info.get('name', 'unknown')}: {e}")
        return None


def build_variable_definitions(variables):
    """
    Build GraphQL variable definitions from variables dict
    """
    definitions = []
    for var_name, var_value in variables.items():
        if var_name == 'first':
            definitions.append("$first: Int!")
        elif var_name == 'constraints':
            definitions.append("$constraints: AdvancedNameSearchConstraints")  # Could be made more dynamic
        elif var_name == 'id':
            definitions.append("$id: ID!")
        elif var_name == 'searchText':
            definitions.append("$searchText: String!")
        else:
            definitions.append(f"${var_name}: String")

    return ', '.join(definitions)


def build_example_constraints(constraint_type):
    """
    Build example constraint object based on introspected constraint type
    """
    clean_type = constraint_type.replace('!', '').strip()

    if clean_type not in detailed_introspection_data:
        return {"searchTerm": "example"}

    constraint_data = detailed_introspection_data[clean_type]
    constraint_fields = constraint_data.get('fields', [])

    example_constraints = {}

    for field in constraint_fields[:3]:  # Limit to 3 constraint fields
        field_name = field['name']

        if 'text' in field_name.lower():
            example_constraints[field_name] = {"searchTerm": "example search"}
        elif 'year' in field_name.lower():
            example_constraints[field_name] = {"start": 1990, "end": 2000}
        elif 'date' in field_name.lower():
            example_constraints[field_name] = {"start": "1990-01-01", "end": "2000-12-31"}
        elif 'profession' in field_name.lower():
            example_constraints[field_name] = {"anyProfessions": ["ACTOR"]}
        elif 'gender' in field_name.lower():
            example_constraints[field_name] = "MALE"

    return example_constraints if example_constraints else {"searchTerm": "example"}


def find_input_types_from_discovered():
    """
    Find input types from the already discovered argument types
    """
    print("\nAnalyzing discovered argument types...")

    input_types = set()
    enum_types = set()

    # Look through all discovered types for input/enum types
    for type_name, type_data in detailed_introspection_data.items():
        # Check the argument types we've already collected
        argument_types = type_data.get('argument_types', [])
        for arg_type in argument_types:
            if 'Constraint' in arg_type or 'Search' in arg_type or 'Filter' in arg_type or 'Sort' in arg_type:
                input_types.add(arg_type)
            elif arg_type.endswith('Type') or arg_type.endswith('Order') or arg_type.endswith('Status'):
                enum_types.add(arg_type)

    # Also check related types
    for type_name, type_data in detailed_introspection_data.items():
        related_types = type_data.get('related_types', [])
        for rel_type in related_types:
            if 'Constraint' in rel_type or 'Search' in rel_type or 'Filter' in rel_type:
                input_types.add(rel_type)

    constraint_types = sorted(list(input_types))
    enum_types = sorted(list(enum_types))

    print(f"Found {len(constraint_types)} potential constraint types from discovered arguments:")
    for constraint_type in constraint_types:
        print(f"   - {constraint_type}")

    print(f"\nFound {len(enum_types)} potential enum types:")
    for enum_type in enum_types:
        print(f"   - {enum_type}")

    return constraint_types, enum_types


def introspect_input_types():
    """
    Introspect input types to find available constraint options
    """
    try:
        constraint_types, enum_types = find_input_types_from_discovered()

        if constraint_types:
            print(f"\nIntrospecting {len(constraint_types)} discovered constraint types...")
            for i, constraint_type in enumerate(constraint_types, 1):
                if constraint_type not in introspected_types:
                    constraint_group_info = {
                        "current": i,
                        "total": len(constraint_types),
                        "group_name": "discovered constraints"
                    }
                    print(f"({i}/{len(constraint_types)}) Introspecting {constraint_type}:")
                    fetch_introspection_data(constraint_type, group_info=constraint_group_info)
                else:
                    print(f"({i}/{len(constraint_types)}) {constraint_type} already introspected")

        # Also introspect enum types with progress tracking
        if enum_types:
            print(f"\nIntrospecting {len(enum_types)} discovered enum types...")
            for i, enum_type in enumerate(enum_types, 1):
                if enum_type not in introspected_types:
                    enum_group_info = {
                        "current": i,
                        "total": len(enum_types),
                        "group_name": "enum types"
                    }
                    print(f"({i}/{len(enum_types)}) Introspecting {enum_type}:")
                    fetch_introspection_data(enum_type, group_info=enum_group_info)
                else:
                    print(f"({i}/{len(enum_types)}) {enum_type} already introspected")
        else:
            print("No enum types discovered from arguments")

    except Exception as e:
        print(f"Error in introspect_input_types: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")


def find_constraint_patterns():
    """
    Analyze the Query type fields to find constraint patterns
    """
    print("\nAnalyzing Query fields for constraint patterns...")

    if 'Query' not in detailed_introspection_data:
        print("Query type not found in introspected data")
        return

    query_data = detailed_introspection_data['Query']
    query_fields = query_data.get('fields', [])

    constraint_info = {}

    for field in query_fields:
        field_name = field['name']
        args = field.get('args', [])

        if args:
            constraint_args = []
            for arg in args:
                arg_name = arg['name']
                arg_type = arg['type']

                if 'constraint' in arg_name.lower() or 'filter' in arg_name.lower():
                    constraint_args.append({
                        'name': arg_name,
                        'type': arg_type,
                        'description': arg.get('description', '')
                    })

            if constraint_args:
                constraint_info[field_name] = {
                    'return_type': field['type'],
                    'constraints': constraint_args
                }

    print(f"Found {len(constraint_info)} Query fields with constraints:")
    for field_name, info in constraint_info.items():
        print(f"\n{field_name}:")
        print(f"   Returns: {info['return_type']}")
        for constraint in info['constraints']:
            print(f"   Constraint: {constraint['name']} ({constraint['type']})")
            if constraint['description']:
                print(f"      Description: {constraint['description'][:100]}...")

    return constraint_info


def find_missing_types():
    """
    Find types that are referenced but not yet introspected
    """
    missing_types = set()

    # Check all related and argument types from existing data
    for type_data in detailed_introspection_data.values():
        # Check related types
        related_types = type_data.get('related_types', [])
        argument_types = type_data.get('argument_types', [])
        all_related = set(related_types + argument_types)

        for related_type in all_related:
            if (related_type not in introspected_types and
                not related_type.startswith('__') and
                    related_type not in ['String', 'Int', 'Float', 'Boolean', 'ID']):
                missing_types.add(related_type)

    # Also check argument types directly from Query fields
    if 'Query' in detailed_introspection_data:
        query_fields = detailed_introspection_data['Query'].get('fields', [])

        for field in query_fields:
            args = field.get('args', [])
            for arg in args:
                arg_type_raw = arg.get('type', '')
                # Clean up the type name (remove ! and [])
                arg_type_clean = arg_type_raw.replace('!', '').replace('[', '').replace(']', '').strip()

                # Check if this argument type needs introspection
                if (arg_type_clean and
                    arg_type_clean not in introspected_types and
                    not arg_type_clean.startswith('__') and
                        arg_type_clean not in ['String', 'Int', 'Float', 'Boolean', 'ID']):
                    missing_types.add(arg_type_clean)

                    print(f"  Found missing argument type: {arg_type_clean} (from {field['name']}.{arg['name']})")

    constraint_keywords = ['Constraint', 'Search', 'Sort', 'Filter', 'Input']
    for type_data in detailed_introspection_data.values():
        fields = type_data.get('fields', [])
        for field in fields:
            # Check field args for constraint types
            args = field.get('args', [])
            for arg in args:
                arg_type = arg.get('type', '')
                # Extract clean type name
                clean_type = arg_type.replace('!', '').replace('[', '').replace(']', '').strip()

                # Check if it looks like a constraint type
                if any(keyword in clean_type for keyword in constraint_keywords):
                    if (clean_type not in introspected_types and
                        not clean_type.startswith('__') and
                            clean_type not in ['String', 'Int', 'Float', 'Boolean', 'ID']):
                        missing_types.add(clean_type)
                        print(f"  Found missing constraint type: {clean_type}")

    # Check for commonly expected constraint types
    expected_constraint_types = [
        'AdvancedNameSearchConstraints',
        'AdvancedTitleSearchConstraints',
        'NameTextConstraint',
        'TitleTextConstraint',
        'AdvancedNameSearchSort',
        'AdvancedTitleSearchSort'
    ]

    for expected_type in expected_constraint_types:
        if expected_type not in introspected_types:
            # Only add if we have some evidence it exists (referenced somewhere)
            for type_data in detailed_introspection_data.values():
                all_refs = (type_data.get('related_types', []) +
                            type_data.get('argument_types', []) +
                            type_data.get('all_related_types', []))
                if expected_type in all_refs:
                    missing_types.add(expected_type)
                    print(f"  Found expected constraint type: {expected_type}")
                    break

    missing_list = sorted(list(missing_types))

    if missing_list:
        print(f"\nFound {len(missing_list)} missing types:")
        for missing_type in missing_list:
            print(f"  - {missing_type}")

    return missing_list


def introspect_all_discovered_argument_types():
    """
    After Query introspection, find and introspect all argument types that were discovered
    """
    print("\nDiscovering all argument types from Query fields...")

    if 'Query' not in detailed_introspection_data:
        print("Query type not found - cannot discover argument types")
        return

    query_data = detailed_introspection_data['Query']
    query_fields = query_data.get('fields', [])

    all_argument_types = set()
    constraint_types = set()

    # Collect all argument types from Query fields
    for field in query_fields:
        args = field.get('args', [])
        for arg in args:
            arg_type_raw = arg.get('type', '')
            # Clean up the type name
            arg_type_clean = arg_type_raw.replace('!', '').replace('[', '').replace(']', '').strip()

            if (arg_type_clean and
                not arg_type_clean.startswith('__') and
                    arg_type_clean not in ['String', 'Int', 'Float', 'Boolean', 'ID']):
                all_argument_types.add(arg_type_clean)

                # Check if it's a constraint type
                if any(kw in arg_type_clean for kw in ['Constraint', 'Search', 'Sort', 'Filter', 'Input']):
                    constraint_types.add(arg_type_clean)

    print(f"Found {len(all_argument_types)} total argument types")
    print(f"Found {len(constraint_types)} constraint types")

    # Show constraint types with status
    if constraint_types:
        print("\nConstraint types to introspect:")
        for ct in sorted(constraint_types):
            status = "done" if ct in introspected_types else "⏳ pending"
            print(f"   - {ct} ({status})")

    # Introspect missing constraint types with progress tracking
    missing_constraints = [ct for ct in constraint_types if ct not in introspected_types]
    if missing_constraints:
        print(f"\nIntrospecting {len(missing_constraints)} missing constraint types...")
        for i, constraint_type in enumerate(sorted(missing_constraints), 1):
            constraint_group_info = {
                "current": i,
                "total": len(missing_constraints),
                "group_name": "missing constraints"
            }
            print(f"\n({i}/{len(missing_constraints)}) Introspecting: {constraint_type}")
            fetch_introspection_data(constraint_type, depth=0, group_info=constraint_group_info)

            # Verify it was introspected
            if constraint_type in detailed_introspection_data:
                field_count = detailed_introspection_data[constraint_type].get('field_count', 0)
                kind = detailed_introspection_data[constraint_type].get('kind', 'Unknown')
                print(f"   Success! {constraint_type} ({kind}) with {field_count} fields")
            else:
                print(f"   Failed to introspect {constraint_type}")
    else:
        print("All constraint types already introspected!")

    # Also introspect other important argument types with progress tracking
    other_argument_types = [t for t in all_argument_types if t not in constraint_types and t not in introspected_types]
    if other_argument_types:
        important_others = [t for t in other_argument_types if any(kw in t for kw in ['Text', 'Date', 'MonthDay', 'Sort', 'Order'])]

        if important_others:
            print(f"\nFound {len(important_others)} other important argument types:")
            for ot in sorted(important_others):
                print(f"   - {ot}")

            print(f"\nIntrospecting {len(important_others)} important argument types...")
            for i, arg_type in enumerate(sorted(important_others)[:10], 1):
                if arg_type not in introspected_types:
                    arg_group_info = {
                        "current": i,
                        "total": min(len(important_others), 10),
                        "group_name": "important args"
                    }
                    print(f"({i}/{min(len(important_others), 10)}) Introspecting: {arg_type}")
                    fetch_introspection_data(arg_type, depth=0, group_info=arg_group_info)


def introspect_missing_related_types():
    """
    Find and introspect types that are referenced but haven't been introspected yet
    """
    global introspection_counter

    print("\nLooking for missing related types...")

    all_referenced_types = set()

    # Collect all type references from existing data
    for type_name, type_data in detailed_introspection_data.items():
        # Get types from related_types lists
        related_types = type_data.get('related_types', [])
        argument_types = type_data.get('argument_types', [])
        all_related_types = type_data.get('all_related_types', [])
        all_referenced_types.update(related_types)
        all_referenced_types.update(argument_types)
        all_referenced_types.update(all_related_types)

        # Also extract types from field types directly
        fields = type_data.get('fields', [])
        for field in fields:
            field_type = field.get('type', '')
            # Extract type names from field types
            extracted_types = extract_type_names_from_string(field_type)
            all_referenced_types.update(extracted_types)

    # Find types that are referenced but not introspected
    missing_types = []
    for ref_type in all_referenced_types:
        if (ref_type and
            ref_type not in introspected_types and
            not ref_type.startswith('__') and
                ref_type not in ['String', 'Int', 'Float', 'Boolean', 'ID']):
            missing_types.append(ref_type)

    missing_types = sorted(list(set(missing_types)))

    if missing_types:
        print(f"Found {len(missing_types)} missing related types:")

        # Categorize the missing types
        connection_types = [t for t in missing_types if 'Connection' in t]
        constraint_types = [t for t in missing_types if any(kw in t for kw in ['Constraint', 'Search', 'Sort', 'Filter', 'Input'])]
        edge_types = [t for t in missing_types if 'Edge' in t]
        text_types = [t for t in missing_types if 'Text' in t]
        other_types = [t for t in missing_types if t not in connection_types + constraint_types + edge_types + text_types]

        print(f"  Connection types ({len(connection_types)}): {connection_types[:5]}{'...' if len(connection_types) > 5 else ''}")
        print(f"  Constraint types ({len(constraint_types)}): {constraint_types[:5]}{'...' if len(constraint_types) > 5 else ''}")
        print(f"  Text types ({len(text_types)}): {text_types[:5]}{'...' if len(text_types) > 5 else ''}")
        print(f"  Edge types ({len(edge_types)}): {edge_types[:5]}{'...' if len(edge_types) > 5 else ''}")
        print(f"  Other types ({len(other_types)}): {other_types[:5]}{'...' if len(other_types) > 5 else ''}")

        # Introspect the most important missing types automatically with progress tracking
        priority_types = constraint_types + text_types + [t for t in connection_types if 'Known' in t]

        if priority_types:
            print(f"\nAuto-introspecting {len(priority_types)} high-priority missing types...")
            print(f"   Starting from introspection #{introspection_counter + 1}")

            success_count = 0
            for i, missing_type in enumerate(priority_types, 1):
                if missing_type not in introspected_types:
                    priority_group_info = {
                        "current": i,
                        "total": len(priority_types),
                        "group_name": "priority missing"
                    }
                    print(f"\n({i}/{len(priority_types)}) Introspecting: {missing_type}")
                    try:
                        fetch_introspection_data(missing_type, depth=0, group_info=priority_group_info)

                        # Check if introspection was successful
                        if missing_type in detailed_introspection_data:
                            field_count = detailed_introspection_data[missing_type].get('field_count', 0)
                            kind = detailed_introspection_data[missing_type].get('kind', 'Unknown')
                            print(f"   Success! {missing_type} ({kind}) with {field_count} fields")
                            success_count += 1
                        else:
                            print(f"   Failed to introspect {missing_type}")
                    except Exception as e:
                        print(f"   Error introspecting {missing_type}: {e}")
                else:
                    print(f"   {missing_type} already introspected")

            print(f"\nAuto-introspection completed: {success_count}/{len(priority_types)} types successfully introspected")
            print(f"   Total introspections so far: {introspection_counter}")

            if success_count > 0:
                print("Saving updated results...")
                save_detailed_results()

        # Handle remaining types with progress tracking
        remaining_types = [t for t in missing_types if t not in priority_types]
        if remaining_types:
            try:
                print(f"\nIntrospecting remaining {len(remaining_types)} types...")
                print(f"   Continuing from introspection #{introspection_counter + 1}")

                for i, missing_type in enumerate(remaining_types, 1):
                    if missing_type not in introspected_types:
                        remaining_group_info = {
                            "current": i,
                            "total": len(remaining_types),
                            "group_name": "remaining types"
                        }
                        print(f"\n({i}/{len(remaining_types)}) Introspecting: {missing_type}")
                        try:
                            fetch_introspection_data(missing_type, depth=0, group_info=remaining_group_info)
                            if missing_type in detailed_introspection_data:
                                field_count = detailed_introspection_data[missing_type].get('field_count', 0)
                                print(f"   Success! {field_count} fields (total: {introspection_counter})")
                            else:
                                print(f"   Failed (total: {introspection_counter})")
                        except Exception as e:
                            print(f"   Error: {e}")

                print(f"\nSaving final results... (Total introspections: {introspection_counter})")
                save_detailed_results()
            except KeyboardInterrupt:
                print(f"\nSkipping remaining types (Completed: {introspection_counter} introspections)")
    else:
        print("No missing related types found - all referenced types are introspected")
        print(f"   Total introspections completed: {introspection_counter}")


def extract_type_names_from_string(type_string):
    """
    Extract type names from a GraphQL type string like 'NameKnownForConnection!' or '[String!]!'
    """
    if not type_string:
        return set()

    # Remove GraphQL syntax
    clean_string = type_string.replace('!', '').replace('[', '').replace(']', '').strip()

    # Skip built-in types
    if clean_string in ['String', 'Int', 'Float', 'Boolean', 'ID']:
        return set()

    # Return the clean type name
    if clean_string and not clean_string.startswith('__'):
        return {clean_string}

    return set()


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='IMDb GraphQL Introspection Tool - Discover and analyze the IMDb GraphQL API schema',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate example query for a specific type
  python introspection.py --example Title tt0415267

  # Generate example query for a search operation
  python introspection.py --example advancedNameSearch "Brad Pitt"
  python introspection.py --example advancedTitleSearch "The Matrix"

  # Run full introspection (interactive mode)
  python introspection.py

Generated Files:
  - comprehensive_introspection_results.json: Complete detailed results
  - readable_introspection_results.json: Simplified field mappings
  - introspection_report.md: Human-readable summary
  - query_examples.md: Working GraphQL query examples
  - example_*.md: Specific type/operation examples (when using --example)

Note: The script uses rate limiting (0.5s between API calls) to respect the API.
        """
    )

    parser.add_argument(
        '--example',
        nargs=2,
        metavar=('TYPE_OR_OPERATION', 'ID_OR_SEARCH'),
        help="""Generate example query for a specific type or operation.

For types: --example Title tt0415267
For operations: --example advancedNameSearch "Brad Pitt"

Available types: Title, Name, Person, Company, etc.
Available operations: advancedNameSearch, advancedTitleSearch, mainSearch, etc.

The tool will automatically detect whether you're requesting a type or operation
and generate appropriate examples with full field documentation."""
    )

    return parser.parse_args()


def main():
    """Main function with argument parsing"""
    global detailed_introspection_data, introspection_counter, total_types_to_introspect

    # Reset counters
    introspection_counter = 0
    total_types_to_introspect = 0

    # Parse arguments
    args = parse_arguments()

    start_time = time.time()

    print("Starting GraphQL Type Introspection")
    print(f"Rate limiting: 1 API call per {RATE_LIMIT_DELAY} seconds")
    if args.example:
        print(f"Generating example for: {args.example[0]} with ID {args.example[1]}")
    print("=" * 60)

    # Load existing data
    filename = 'comprehensive_introspection_results.json'
    if os.path.exists(filename):
        print(f"Loading existing introspection data from {filename}...")
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Handle different data formats
            if isinstance(data, dict):
                if 'detailed_types' in data:
                    detailed_introspection_data = data['detailed_types']
                    print("Loaded new format data")
                elif 'Query' in data or len(data) > 0:
                    detailed_introspection_data = data
                    print("Loaded direct format data")
                else:
                    print("Unknown data format, starting fresh")
                    detailed_introspection_data = {}
            else:
                print("Invalid data format, starting fresh")
                detailed_introspection_data = {}

            # Update introspected types set
            if detailed_introspection_data:
                introspected_types.update(detailed_introspection_data.keys())
                print(f"Loaded {len(detailed_introspection_data)} types from existing data")

                # If user requested specific example, generate it immediately
                if args.example:
                    print("\nGenerating requested example query...")
                    generate_query_examples(args)
                    return 0

                # Show what we loaded with consistent categorization
                categories = categorize_types_consistently(detailed_introspection_data)

                # Show both GraphQL kind breakdown and name-based breakdown
                kind_counts = {}
                for type_data in detailed_introspection_data.values():
                    if isinstance(type_data, dict):
                        kind = type_data.get('kind', 'Unknown')
                        kind_counts[kind] = kind_counts.get(kind, 0) + 1

                print(f"GraphQL Kind breakdown: {dict(kind_counts)}")
                print("Name-based breakdown:")
                print(f"    Query: {len(categories['query_types'])}, Objects: {len(categories['object_types'])}")
                print(f"    Connections: {len(categories['connection_types'])}, Inputs: {len(categories['input_types'])}")
                print(f"    Enums: {len(categories['enum_types'])}, Others: {len(categories['other_types'])}")
            else:
                print("No valid data found in file")

        except json.JSONDecodeError as e:
            print(f"Error reading JSON file: {e}")
            print("Starting fresh introspection...")
            detailed_introspection_data = {}
        except Exception as e:
            print(f"Error loading existing data: {e}")
            print("Starting fresh introspection...")
            detailed_introspection_data = {}
    else:
        print("No existing data found, starting fresh...")
        detailed_introspection_data = {}

    # If user requested example but we don't have data, inform them
    if args.example and not detailed_introspection_data:
        print("Cannot generate example - no introspection data available")
        print("Run the script without --example first to perform introspection")
        return 1

    # If we have existing data, offer options
    if detailed_introspection_data:
        print(f"\nFound existing data with {len(detailed_introspection_data)} types.")
        print("What would you like to do?")
        print("1. Use existing data as-is (fast)")
        print("2. Update existing data with missing types")
        print("3. Perform fresh introspection (slow)")
        print("4. Generate reports only")

        try:
            choice = int(input("\nEnter your choice (1-4): "))
        except (ValueError, KeyboardInterrupt):
            print("\nUsing existing data as-is")
            choice = 1

        if choice == 1:
            print("Using existing data without updates")
        elif choice == 2:
            print("Updating existing data...")
            # Check for missing constraint types and introspect them
            key_constraints = ['AdvancedNameSearchConstraints', 'AdvancedTitleSearchConstraints', 'NewsCategoryConstraints', 'NameTextConstraint', 'TitleTextConstraint']
            missing_constraints = [c for c in key_constraints if c not in introspected_types]

            if missing_constraints:
                print(f"Found {len(missing_constraints)} missing constraint types:")
                for constraint in missing_constraints:
                    print(f"   - {constraint}")

                print("\nIntrospecting missing constraint types...")
                for constraint_type in missing_constraints:
                    print(f"Introspecting: {constraint_type}")
                    fetch_introspection_data(constraint_type, depth=0)

                # Also run missing types check
                introspect_missing_related_types()

                # Save updated data
                print("\nSaving updated results...")
                save_detailed_results()
            else:
                print("All key constraint types already present")

        elif choice == 3:
            print("Performing fresh introspection...")
            detailed_introspection_data = {}
            introspected_types.clear()

            print("\n1. Introspecting Query type first...")
            fetch_introspection_data('Query')

            print("\n2. Discovering and introspecting all argument types...")
            introspect_all_discovered_argument_types()

            print("\n3. Running additional constraint discovery...")
            introspect_input_types()

            print("\n4. Checking for missing related types...")
            introspect_missing_related_types()

            # Save results
            print("\nSaving detailed results...")
            save_detailed_results()

            # Generate markdown report
            print("\nGenerating markdown report...")
            generate_markdown_report()

        elif choice == 4:
            print("Generating reports only...")

    else:
        # No existing data, perform fresh introspection
        print("\nStarting comprehensive fresh introspection...")
        print("1. Introspecting Query type first...")
        fetch_introspection_data('Query')

        print("\n2. Discovering and introspecting all argument types...")
        introspect_all_discovered_argument_types()

        print("\n3. Running additional constraint discovery...")
        introspect_input_types()

        print("\n4. Checking for missing related types...")
        introspect_missing_related_types()

        # Save results
        print("\nSaving detailed results...")
        save_detailed_results()

        # Generate markdown report
        print("\nGenerating markdown report...")
        generate_markdown_report()

    # Generate query examples using dynamic functions
    print("\nGenerating dynamic query examples...")
    generate_query_examples()

    # Generate dynamic examples
    print("\nGenerating enhanced dynamic query examples...")
    generate_dynamic_query_examples()

    # Show execution time
    end_time = time.time()
    execution_time = end_time - start_time
    print(f"\nTotal execution time: {execution_time:.2f} seconds")

    # Show constraint types status
    print("\nConstraint Types Status:")
    key_constraints = ['AdvancedNameSearchConstraints', 'AdvancedTitleSearchConstraints', 'NewsCategoryConstraints', 'NameTextConstraint', 'TitleTextConstraint']
    for constraint_type in key_constraints:
        if constraint_type in introspected_types:
            if constraint_type in detailed_introspection_data:
                type_data = detailed_introspection_data[constraint_type]
                # Handle both old and new data structures
                if isinstance(type_data, dict):
                    field_count = type_data.get('field_count', 0)
                    kind = type_data.get('kind', 'Unknown')
                    print(f"   {constraint_type} ({kind}, {field_count} fields)")
                else:
                    print(f"   {constraint_type} (introspected)")
            else:
                print(f"   {constraint_type} (in types list)")
        else:
            print(f"   {constraint_type} (not introspected)")

    # Show consistent type summary
    categories = categorize_types_consistently(detailed_introspection_data)
    print("\nFinal Type Summary:")
    print(f"   Total Types: {len(detailed_introspection_data)}")
    print(f"   Query Types: {len(categories['query_types'])}")
    print(f"   Object Types: {len(categories['object_types'])}")
    print(f"   Connection Types: {len(categories['connection_types'])}")
    print(f"   Input Types: {len(categories['input_types'])}")
    print(f"   Enum Types: {len(categories['enum_types'])}")
    print(f"   Other Types: {len(categories['other_types'])}")

    # Show completeness check (with error handling)
    print("\nData Completeness Check:")
    try:
        all_referenced = set()

        for type_name, type_data in detailed_introspection_data.items():
            # Handle both old and new data structures
            if isinstance(type_data, dict):
                all_referenced.update(type_data.get('related_types', []))
                all_referenced.update(type_data.get('argument_types', []))
                all_referenced.update(type_data.get('all_related_types', []))

        missing_refs = [t for t in all_referenced if t not in introspected_types and not t.startswith('__') and t not in ['String', 'Int', 'Float', 'Boolean', 'ID']]

        if missing_refs:
            print(f"   {len(missing_refs)} referenced types still not introspected")
            print(f"   Examples: {missing_refs[:5]}")
        else:
            print("   All referenced types have been introspected")

    except Exception as e:
        print(f"   Could not check completeness: {e}")
        print(f"   Data structure: {type(detailed_introspection_data)}")
        if detailed_introspection_data:
            sample_key = next(iter(detailed_introspection_data))
            sample_value = detailed_introspection_data[sample_key]
            print(f"   Sample data type: {type(sample_value)}")

    # Show file status
    print("\nGenerated files:")
    file_list = [
        'comprehensive_introspection_results.json',
        'readable_introspection_results.json',
        'introspection_report.md',
        'query_examples.md',
        'dynamic_query_examples.md',
        'constraint_guide.md'
    ]

    for filename in file_list:
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            size_str = f"{size:,} bytes" if size < 1024*1024 else f"{size/(1024*1024):.1f} MB"
            print(f"   {filename} ({size_str})")
        else:
            print(f"   {filename} (not generated)")

    # Show usage tips
    print("\nNext time you can:")
    print("   • Run with existing data for faster execution")
    print("   • Use option 2 to update missing constraint types")
    print("   • Check the generated markdown files for schema documentation")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        print(f"Partial results: {len(introspected_types)} types introspected")
        save_detailed_results()
        sys.exit(1)
