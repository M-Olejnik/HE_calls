"""
app.py (updated for Streamlit Cloud with GitHub persistence)

Streamlit app for labeling files from final_output_2.
Labels are persisted to GitHub using the GitHub API.

Each user gets their own label file: final_labels_{username}.csv

Usage:
    streamlit run app.py
"""

import streamlit as st
import os
import glob
import re
import pandas as pd
import base64
import requests

st.set_page_config(layout="wide", page_title="Final Output Labeler")

ROOT = os.getcwd()
FINAL_OUTPUT_DIR = os.path.join(ROOT, "final_output_2")
CLUSTERS = ["health", "civil", "climate", "culture", "digital", "food"]
LABEL_COLS = ["NLP", "WUDAP", "ETHICS", "ENVIRO", "OPERATIONS", "none"]


def load_labels_from_github(github_token, github_repo, username, branch="main"):
    """Load labels from GitHub repository"""
    csv_filename = f"final_labels_{username}.csv"
    url = f"https://api.github.com/repos/{github_repo}/contents/{csv_filename}?ref={branch}"
    
    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3.raw"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            # Parse CSV from response
            df = pd.read_csv(pd.io.common.StringIO(response.text))
            result = {}
            for _, row in df.iterrows():
                call_id = row.get("CallID")
                if call_id:
                    result[call_id] = {col: row.get(col, "") for col in LABEL_COLS}
            return result
    except Exception as e:
        st.warning(f"Could not load from GitHub: {e}")
    
    return {}


def save_labels_to_github(github_token, github_repo, username, labels_dict, branch="main"):
    """Save labels to GitHub repository"""
    csv_filename = f"final_labels_{username}.csv"
    
    # Prepare CSV content
    rows = []
    for call_id, label_dict in sorted(labels_dict.items()):
        row = {"CallID": call_id}
        for col in LABEL_COLS:
            row[col] = label_dict.get(col, "")
        rows.append(row)
    
    df = pd.DataFrame(rows)
    csv_content = df.to_csv(index=False)
    
    # Encode content in base64
    encoded_content = base64.b64encode(csv_content.encode()).decode()
    
    url = f"https://api.github.com/repos/{github_repo}/contents/{csv_filename}"
    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json"}
    
    # Get current file SHA (needed for updates)
    try:
        get_response = requests.get(url, headers=headers, params={"ref": branch})
        sha = get_response.json().get("sha") if get_response.status_code == 200 else None
    except:
        sha = None
    
    # Prepare commit data
    data = {
        "message": f"Update labels for {username}",
        "content": encoded_content,
        "branch": branch
    }
    if sha:
        data["sha"] = sha
    
    try:
        response = requests.put(url, json=data, headers=headers)
        if response.status_code in [201, 200]:
            return True
        else:
            st.error(f"GitHub save failed: {response.status_code}")
            return False
    except Exception as e:
        st.error(f"Error saving to GitHub: {e}")
        return False


def extract_page_number(divide_file_path, call_id):
    """Extract page number for a call_id from the divide file"""
    try:
        with open(divide_file_path, "r", encoding="utf-8") as f:
            text = f.read()
        # Look for lines containing the call_id and extract the page number
        # Format: CALL_ID: ... page_number
        pattern = rf"{re.escape(call_id)}:.*?\.+\s*(\d+)"
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return 10**9  # Return large number if not found


def get_sorted_files(cluster_dir, cluster, root_dir):
    """Get files sorted by page number from divide file"""
    txt_files = glob.glob(os.path.join(cluster_dir, "*.txt"))
    divide_file_path = os.path.join(root_dir, cluster, f"divide_{cluster}.txt")
    
    if not os.path.exists(divide_file_path):
        # Fallback to alphabetical sorting
        return sorted(txt_files)
    
    # Sort by page number
    def get_page_sort_key(file_path):
        fname = os.path.basename(file_path)
        call_id = fname.replace(".txt", "")
        page_num = extract_page_number(divide_file_path, call_id)
        return (page_num, fname)
    
    return sorted(txt_files, key=get_page_sort_key)


def get_destination_mapping(divide_file_path):
    """Parse divide file to map call_ids to their destinations"""
    destination_map = {}
    try:
        with open(divide_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        current_destination = None
        for line in lines:
            stripped = line.strip()
            # Check if this is a destination header line (contains "Destination")
            if stripped.startswith("Destination"):
                # Extract destination text (remove page number at the end if present)
                current_destination = re.sub(r'\.+\s*\d+\s*$', '', stripped).replace("Destination ", "").strip()
            # Check if this is a call_id line
            elif stripped.startswith("HORIZON-"):
                # Extract call_id (everything before the colon)
                match = re.match(r'^(HORIZON-[^:]+):', stripped)
                if match and current_destination:
                    call_id = match.group(1)
                    destination_map[call_id] = current_destination
    except Exception:
        pass
    
    return destination_map


def main():
    if not os.path.isdir(FINAL_OUTPUT_DIR):
        st.error(f"final_output_2 directory not found at {FINAL_OUTPUT_DIR}")
        st.stop()

    # GitHub configuration (use Streamlit secrets if available)
    github_token = st.secrets.get("github_token", "") if hasattr(st, "secrets") else ""
    github_repo = st.secrets.get("github_repo", "") if hasattr(st, "secrets") else ""
    
    # If not in secrets, ask user (for local testing)
    if not github_token:
        st.sidebar.header("GitHub Configuration")
        github_token = st.sidebar.text_input("GitHub Personal Access Token:", type="password")
        github_repo = st.sidebar.text_input("GitHub Repo (owner/repo):", "")
        
        if not github_token or not github_repo:
            st.warning("⚠️ Please configure GitHub credentials in sidebar (or add to Streamlit secrets)")
            st.info("""
            **To set up GitHub persistence:**
            1. Create a GitHub Personal Access Token (Settings → Developer → Personal Access Tokens)
            2. Give it `repo` scope permission
            3. Add to Streamlit secrets:
               - In `.streamlit/secrets.toml`: `github_token = "your_token"` and `github_repo = "owner/repo"`
               - Or in Streamlit Cloud settings
            """)
            st.stop()
    
    # Username input
    username = st.text_input("Enter your username:", "")
    if not username:
        st.warning("Please enter a username to get started")
        st.stop()

    st.title("Final Output Labeler")

    # Store GitHub credentials in session state for access in button callbacks
    st.session_state.github_token = github_token
    st.session_state.github_repo = github_repo
    st.session_state.username = username

    # Initialize session state
    if "labels_dict" not in st.session_state:
        st.session_state.labels_dict = load_labels_from_github(github_token, github_repo, username)
    if "viewed_calls" not in st.session_state:
        st.session_state.viewed_calls = set()
    if "last_call_id" not in st.session_state:
        st.session_state.last_call_id = None
    if "destination_map" not in st.session_state:
        st.session_state.destination_map = {}

    # Sidebar: cluster selection
    st.sidebar.header("Navigation")
    selected_cluster = st.sidebar.selectbox("Select Cluster", CLUSTERS)
    
    cluster_dir = os.path.join(FINAL_OUTPUT_DIR, selected_cluster)
    
    if not os.path.isdir(cluster_dir):
        st.error(f"Cluster directory not found: {cluster_dir}")
        st.stop()
    
    # Get all txt files in the cluster, sorted by page number from divide file
    txt_files = get_sorted_files(cluster_dir, selected_cluster, ROOT)
    
    # Load destination mapping for this cluster
    divide_file_path = os.path.join(ROOT, selected_cluster, f"divide_{selected_cluster}.txt")
    st.session_state.destination_map = get_destination_mapping(divide_file_path)
    
    if not txt_files:
        st.warning(f"No txt files found in {selected_cluster}/")
        st.stop()
    
    # State tracking
    if "cluster_index" not in st.session_state or st.session_state.get("last_cluster") != selected_cluster:
        st.session_state.cluster_index = 0
        st.session_state.last_cluster = selected_cluster

    num_files = len(txt_files)
    idx = st.sidebar.slider("File", 0, num_files - 1, st.session_state.cluster_index)
    st.session_state.cluster_index = idx

    # Navigation buttons
    col_nav1, col_nav2 = st.sidebar.columns(2)
    if col_nav1.button("⬅ Prev") and st.session_state.cluster_index > 0:
        st.session_state.cluster_index -= 1
        st.rerun()
    if col_nav2.button("Next ➡") and st.session_state.cluster_index < num_files - 1:
        st.session_state.cluster_index += 1
        st.rerun()

    st.sidebar.divider()
    st.sidebar.write(f"**Progress:** {st.session_state.cluster_index + 1} / {num_files}")
    st.sidebar.write(f"**Cluster:** {selected_cluster}")

    # Current file
    current_path = txt_files[st.session_state.cluster_index]
    fname = os.path.basename(current_path)
    call_id = fname.replace(".txt", "")

    # Auto-default previous call to "none" if viewed but not labeled
    if st.session_state.last_call_id and st.session_state.last_call_id != call_id:
        if st.session_state.last_call_id in st.session_state.viewed_calls:
            prev_labels = st.session_state.labels_dict.get(st.session_state.last_call_id, {col: "" for col in LABEL_COLS})
            # Check if any label (except "none") is set
            has_labels = any(prev_labels.get(col) == "yes" for col in LABEL_COLS[:-1])
            if not has_labels:
                # Set to "none"
                prev_labels = {col: "" for col in LABEL_COLS}
                prev_labels["none"] = "yes"
                st.session_state.labels_dict[st.session_state.last_call_id] = prev_labels
                save_labels_to_github(st.session_state.github_token, st.session_state.github_repo, 
                                     st.session_state.username, st.session_state.labels_dict)

    # Mark this call as viewed
    st.session_state.viewed_calls.add(call_id)
    st.session_state.last_call_id = call_id

    # Get destination for this call
    destination = st.session_state.destination_map.get(call_id, "")
    if destination:
        st.header(destination)
    else:
        st.header(f"{selected_cluster}")
    
    st.subheader(call_id)

    # Load file content
    try:
        with open(current_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        content = f"[Error reading file: {e}]"

    # Display content
    st.text_area("File Content", content, height=600, disabled=True)

    # Labeling section
    st.divider()
    st.subheader("Labels")

    # Get current labels for this call_id
    current_labels = st.session_state.labels_dict.get(call_id, {col: "" for col in LABEL_COLS})

    # Display label buttons in columns
    cols = st.columns(len(LABEL_COLS))
    for i, label in enumerate(LABEL_COLS):
        is_active = current_labels.get(label) == "yes"
        btn_label = f"✅ {label}" if is_active else f"⬜ {label}"

        if cols[i].button(btn_label, key=f"btn_{call_id}_{label}"):
            # Toggle logic
            if is_active:
                # Deselecting
                current_labels[label] = ""
            else:
                # Selecting
                if label == "none":
                    # If selecting "none", clear all others
                    current_labels = {col: "" for col in LABEL_COLS}
                    current_labels["none"] = "yes"
                else:
                    # If selecting any other label, remove "none"
                    if current_labels.get("none") == "yes":
                        current_labels["none"] = ""
                    current_labels[label] = "yes"
            
            # Auto-save
            st.session_state.labels_dict[call_id] = current_labels
            save_labels_to_github(st.session_state.github_token, st.session_state.github_repo, 
                                 st.session_state.username, st.session_state.labels_dict)
            st.rerun()

    # Display current labels
    st.write("**Current labels:**")
    active_labels = [label for label in LABEL_COLS if current_labels.get(label) == "yes"]
    if active_labels:
        st.write(", ".join(active_labels))
    else:
        st.write("(none)")


if __name__ == "__main__":
    main()

