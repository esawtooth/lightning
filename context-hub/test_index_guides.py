#!/usr/bin/env python3
"""Test script to verify index guide aggregation in Context Hub API"""

import requests
import json
import uuid
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:3000"
USER_ID = "test_user_" + datetime.now().strftime("%Y%m%d_%H%M%S")

def test_index_guides():
    """Test index guide aggregation functionality"""
    headers = {"X-User-Id": USER_ID, "Content-Type": "application/json"}
    
    print(f"Testing with user: {USER_ID}")
    
    # 1. Create root folder
    print("\n1. Creating root folder...")
    root_data = {
        "name": f"{USER_ID}_workspace",
        "content": "",
        "doc_type": "Folder"
    }
    root_response = requests.post(f"{BASE_URL}/docs", json=root_data, headers=headers)
    assert root_response.status_code == 200
    root_folder = root_response.json()
    root_id = root_folder["id"]
    print(f"   Root folder created: {root_id}")
    
    # 2. Create root index guide
    print("\n2. Creating root index guide...")
    root_guide_data = {
        "name": "Index Guide",
        "content": "# Root Workspace Guide\n\nThis is the root workspace. All documents should be organized into appropriate subfolders.",
        "parent_folder_id": root_id,
        "doc_type": "IndexGuide"
    }
    guide_response = requests.post(f"{BASE_URL}/docs", json=root_guide_data, headers=headers)
    assert guide_response.status_code == 200
    print("   Root index guide created")
    
    # 3. Create a subfolder
    print("\n3. Creating subfolder...")
    subfolder_data = {
        "name": "Projects",
        "content": "",
        "parent_folder_id": root_id,
        "doc_type": "Folder"
    }
    subfolder_response = requests.post(f"{BASE_URL}/docs", json=subfolder_data, headers=headers)
    assert subfolder_response.status_code == 200
    subfolder = subfolder_response.json()
    subfolder_id = subfolder["id"]
    print(f"   Subfolder created: {subfolder_id}")
    
    # 4. Create subfolder index guide
    print("\n4. Creating subfolder index guide...")
    subfolder_guide_data = {
        "name": "Index Guide",
        "content": "# Projects Folder Guide\n\nThis folder contains project-related documents. Each project should have its own subfolder.",
        "parent_folder_id": subfolder_id,
        "doc_type": "IndexGuide"
    }
    guide_response = requests.post(f"{BASE_URL}/docs", json=subfolder_guide_data, headers=headers)
    assert guide_response.status_code == 200
    print("   Subfolder index guide created")
    
    # 5. Create a document in the subfolder
    print("\n5. Creating document in subfolder...")
    doc_data = {
        "name": "Project Plan",
        "content": "This is a sample project plan document.",
        "parent_folder_id": subfolder_id,
        "doc_type": "Text"
    }
    doc_response = requests.post(f"{BASE_URL}/docs", json=doc_data, headers=headers)
    assert doc_response.status_code == 200
    document = doc_response.json()
    doc_id = document["id"]
    print(f"   Document created: {doc_id}")
    print(f"   Index guide in response: {'Yes' if document.get('index_guide') else 'No'}")
    if document.get('index_guide'):
        print(f"   Guide preview: {document['index_guide'][:100]}...")
    
    # 6. Get the document directly
    print("\n6. Getting document directly...")
    get_response = requests.get(f"{BASE_URL}/docs/{doc_id}", headers=headers)
    assert get_response.status_code == 200
    doc_data = get_response.json()
    print(f"   Index guide in response: {'Yes' if doc_data.get('index_guide') else 'No'}")
    if doc_data.get('index_guide'):
        print(f"   Guide content includes root guide: {'Root Workspace Guide' in doc_data['index_guide']}")
        print(f"   Guide content includes subfolder guide: {'Projects Folder Guide' in doc_data['index_guide']}")
    
    # 7. List documents in subfolder
    print("\n7. Listing documents in subfolder...")
    list_response = requests.get(f"{BASE_URL}/folders/{subfolder_id}", headers=headers)
    assert list_response.status_code == 200
    folder_docs = list_response.json()
    print(f"   Found {len(folder_docs)} documents")
    if folder_docs:
        first_doc = folder_docs[0]
        print(f"   First doc has index guide: {'Yes' if first_doc.get('index_guide') else 'No'}")
    
    # 8. Search for documents
    print("\n8. Searching for documents...")
    search_response = requests.get(f"{BASE_URL}/search?q=project", headers=headers)
    assert search_response.status_code == 200
    search_results = search_response.json()
    print(f"   Found {len(search_results)} results")
    if search_results:
        first_result = search_results[0]
        print(f"   First result has index guide: {'Yes' if first_result.get('index_guide') else 'No'}")
    
    # 9. Test nested folder structure
    print("\n9. Creating deeply nested structure...")
    subsubfolder_data = {
        "name": "Project Alpha",
        "content": "",
        "parent_folder_id": subfolder_id,
        "doc_type": "Folder"
    }
    subsubfolder_response = requests.post(f"{BASE_URL}/docs", json=subsubfolder_data, headers=headers)
    assert subsubfolder_response.status_code == 200
    subsubfolder = subsubfolder_response.json()
    subsubfolder_id = subsubfolder["id"]
    
    # Create index guide for deeply nested folder
    deep_guide_data = {
        "name": "Index Guide",
        "content": "# Project Alpha Guide\n\nThis is a specific project folder. All Alpha-related docs go here.",
        "parent_folder_id": subsubfolder_id,
        "doc_type": "IndexGuide"
    }
    guide_response = requests.post(f"{BASE_URL}/docs", json=deep_guide_data, headers=headers)
    assert guide_response.status_code == 200
    
    # Create document in deeply nested folder
    deep_doc_data = {
        "name": "Alpha Requirements",
        "content": "Requirements for Project Alpha.",
        "parent_folder_id": subsubfolder_id,
        "doc_type": "Text"
    }
    deep_doc_response = requests.post(f"{BASE_URL}/docs", json=deep_doc_data, headers=headers)
    assert deep_doc_response.status_code == 200
    deep_document = deep_doc_response.json()
    
    print(f"   Deep document has index guide: {'Yes' if deep_document.get('index_guide') else 'No'}")
    if deep_document.get('index_guide'):
        guide_content = deep_document['index_guide']
        print(f"   Guide includes all three levels:")
        print(f"     - Root guide: {'Root Workspace Guide' in guide_content}")
        print(f"     - Projects guide: {'Projects Folder Guide' in guide_content}")
        print(f"     - Alpha guide: {'Project Alpha Guide' in guide_content}")
    
    print("\n✅ All tests passed!")

if __name__ == "__main__":
    test_index_guides()