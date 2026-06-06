from pathlib import Path


def create_project(client) -> str:
    response = client.post("/api/v1/projects", json={"title": "测试项目", "language": "zh-CN"})
    assert response.status_code == 201
    return response.json()["data"]["project_id"]


def upload_source(client, project_id: str) -> None:
    content = (
        "第1章 开始\n林凡走进考场，四周都在议论他。\n\n"
        "第2章 转折\n苏青出现并叫住林凡。\n\n"
        "第3章 结束\n赵岩看着林凡，没有说话。"
    )
    response = client.post(
        f"/api/v1/projects/{project_id}/source",
        files={"file": ("novel.md", content.encode("utf-8"), "text/markdown")},
    )
    assert response.status_code == 200


def wait_for_task(client, task_id: str) -> dict:
    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    task = response.json()["data"]
    assert task["status"] == "SUCCEEDED"
    return task


def test_full_project_flow_and_export(app_client) -> None:
    project_id = create_project(app_client)
    upload_source(app_client, project_id)

    parse_response = app_client.post(
        f"/api/v1/projects/{project_id}/parse",
        json={"min_chapter_count": 3, "split_mode": "auto"},
    )
    assert parse_response.status_code == 202
    wait_for_task(app_client, parse_response.json()["data"]["task_id"])

    generate_response = app_client.post(
        f"/api/v1/projects/{project_id}/generate",
        json={"target_format": "yaml", "scene_granularity": "standard", "include_report": True},
    )
    assert generate_response.status_code == 202
    generate_task = wait_for_task(app_client, generate_response.json()["data"]["task_id"])
    version_id = generate_task["result"]["current_version_id"]

    script_response = app_client.get(f"/api/v1/projects/{project_id}/script", params={"version_id": version_id})
    assert script_response.status_code == 200
    script = script_response.json()["data"]
    assert script["metadata"]["total_scenes"] >= 1

    export_response = app_client.post(
        f"/api/v1/projects/{project_id}/export",
        json={"version_id": version_id, "format": "yaml", "include_report": True},
    )
    assert export_response.status_code == 202
    export_task = wait_for_task(app_client, export_response.json()["data"]["task_id"])
    assert export_task["result"]["download_url"].startswith("/api/v1/downloads/")


def test_rewrite_creates_new_version(app_client) -> None:
    project_id = create_project(app_client)
    upload_source(app_client, project_id)

    parse_response = app_client.post(
        f"/api/v1/projects/{project_id}/parse",
        json={"min_chapter_count": 3, "split_mode": "auto"},
    )
    wait_for_task(app_client, parse_response.json()["data"]["task_id"])

    generate_response = app_client.post(
        f"/api/v1/projects/{project_id}/generate",
        json={"target_format": "yaml", "scene_granularity": "standard", "include_report": True},
    )
    wait_for_task(app_client, generate_response.json()["data"]["task_id"])

    scenes_response = app_client.get(f"/api/v1/projects/{project_id}/scenes")
    assert scenes_response.status_code == 200
    scene_id = scenes_response.json()["data"]["items"][0]["scene_id"]

    rewrite_response = app_client.post(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}/rewrite",
        json={"instruction": "增强冲突张力，压缩节奏", "create_new_version": True},
    )
    assert rewrite_response.status_code == 202
    task = wait_for_task(app_client, rewrite_response.json()["data"]["task_id"])

    versions_response = app_client.get(f"/api/v1/projects/{project_id}/versions")
    versions = versions_response.json()["data"]["items"]
    assert len(versions) == 2
    assert task["result"]["current_version_id"] == versions[-1]["version_id"]


def test_manual_scene_update_tracks_modified_scenes(app_client) -> None:
    project_id = create_project(app_client)
    upload_source(app_client, project_id)

    parse_response = app_client.post(
        f"/api/v1/projects/{project_id}/parse",
        json={"min_chapter_count": 3, "split_mode": "auto"},
    )
    wait_for_task(app_client, parse_response.json()["data"]["task_id"])

    generate_response = app_client.post(
        f"/api/v1/projects/{project_id}/generate",
        json={"target_format": "yaml", "scene_granularity": "standard", "include_report": True},
    )
    wait_for_task(app_client, generate_response.json()["data"]["task_id"])

    scenes_response = app_client.get(f"/api/v1/projects/{project_id}/scenes")
    scene_id = scenes_response.json()["data"]["items"][0]["scene_id"]
    scene_detail = app_client.get(f"/api/v1/projects/{project_id}/scenes/{scene_id}").json()["data"]

    update_response = app_client.patch(
        f"/api/v1/projects/{project_id}/scenes/{scene_id}",
        json={
            "title": scene_detail["title"],
            "slugline": scene_detail["slugline"],
            "purpose": "更新后的场景目标",
            "beats": scene_detail["beats"],
            "adaptation_notes": scene_detail["adaptation_notes"],
            "change_note": "手工修订",
        },
    )
    assert update_response.status_code == 200

    versions_response = app_client.get(f"/api/v1/projects/{project_id}/versions")
    current_version = versions_response.json()["data"]["items"][-1]
    assert scene_id in current_version["modified_scenes"]
