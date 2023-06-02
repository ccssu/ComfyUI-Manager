import re
import os
import json
from git import Repo
from torchvision.datasets.utils import download_url


def scan_in_file(filename):
    with open(filename, "r") as file:
        code = file.read()

    pattern = r"NODE_CLASS_MAPPINGS\s*=\s*{([^}]*)}"
    regex = re.compile(pattern, re.MULTILINE | re.DOTALL)

    match = regex.search(code)
    if match:
        dict_text = match.group(1)
    else:
        return []

    nodes = set()
    class_dict = {}
    key_value_pairs = re.findall(r"\"([^\"]*)\"\s*:\s*([^,\n]*)", dict_text)
    for key, value in key_value_pairs:
        class_dict[key] = value.strip()

    for key, value in class_dict.items():
        nodes.add(key)

    return nodes


def get_py_file_paths(dirname):
    file_paths = []
    
    for root, dirs, files in os.walk(dirname):
        if ".git" in root or "__pycache__" in root:
            continue

        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                file_paths.append(file_path)

        for subdir in dirs:
            subdir = os.path.join(dirname, subdir)
            sub_files = get_py_file_paths(subdir)
            file_paths.extend(sub_files)
    
    return file_paths


def get_nodes(target_dir):
    py_files = []
    directories = []
    
    for item in os.listdir(target_dir):
        if ".git" in item or "__pycache__" in item:
            continue

        path = os.path.abspath(os.path.join(target_dir, item))
        
        if os.path.isfile(path) and item.endswith(".py"):
            py_files.append(path)
        elif os.path.isdir(path):
            directories.append(path)
    
    return py_files, directories


def get_git_urls_from_json(json_file):
    with open(json_file) as file:
        data = json.load(file)

        custom_nodes = data.get('custom_nodes', [])
        git_clone_files = []
        for node in custom_nodes:
            if node.get('install_type') == 'git-clone':
                files = node.get('files', [])
                if files:
                    git_clone_files.append(files[0])

    return git_clone_files


def get_py_urls_from_json(json_file):
    with open(json_file) as file:
        data = json.load(file)

        custom_nodes = data.get('custom_nodes', [])
        py_files = []
        for node in custom_nodes:
            if node.get('install_type') == 'copy':
                files = node.get('files', [])
                if files:
                    py_files.append(files[0])

    return py_files


def clone_or_pull_git_repository(git_url):
    repo_name = git_url.split("/")[-1].split(".")[0]
    repo_dir = os.path.join(os.getcwd(), ".tmp", repo_name)

    if os.path.exists(repo_dir):
        try:
            repo = Repo(repo_dir)
            origin = repo.remote(name="origin")
            origin.pull()
            repo.git.submodule('update', '--init', '--recursive')
            print(f"Pulling {repo_name}...")
        except Exception as e:
            print(f"Pulling {repo_name} failed: {e}")
    else:
        try:
            repo = Repo.clone_from(git_url, repo_dir, recursive=True)
            print(f"Cloning {repo_name}...")
        except Exception as e:
            print(f"Cloning {repo_name} failed: {e}")


def update_custom_nodes():
    tmp_dir = os.path.join(os.getcwd(), ".tmp")
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)

    node_info = {}

    git_urls = get_git_urls_from_json('custom-node-list.json')

    for url in git_urls:
        name = os.path.basename(url)
        if name.endswith(".git"):
            name = name[:-4]
            
        node_info[name] = url
        clone_or_pull_git_repository(url)

    py_urls = get_py_urls_from_json('custom-node-list.json')

    for url in py_urls:
        name = os.path.basename(url)
        if name.endswith(".py"):
            node_info[name] = url

        download_url(url, ".tmp")
            
    return node_info


def gen_json(node_info):
    node_files, node_dirs = get_nodes(".tmp")

    data = {}
    for dirname in node_dirs:
        py_files = get_py_file_paths(dirname)
        
        nodes = set()
        for py in py_files:
            nodes.update(scan_in_file(py))
        
        dirname = os.path.basename(dirname)

        if len(nodes) > 0:
            nodes = list(nodes)
            nodes.sort()
            
            git_url = node_info[dirname]
            data[git_url] = nodes

    for file in node_files:
        nodes = scan_in_file(file)

        if len(nodes) > 0:
            nodes = list(nodes)
            nodes.sort()

            file = os.path.basename(file)

            if file in node_info:
                url = node_info[file]
                data[url] = nodes
            else:
                print(f"Missing info: {url}")

    json_path = f"extension-node-map.json"
    with open(json_path, "w") as file:
        json.dump(data, file, indent=4, sort_keys=True)


print("### ComfyUI Manager Node Scanner ###")

print("\n# Updating extensions\n")
node_info = update_custom_nodes()

print("\n# 'extension-node-map.json' file is generated.\n")
gen_json(node_info)