def test_task_title_uses_summary_and_preserves_source(client, store):
    task_id = store.create_task(
        name="recording", source_path="/tmp/1cd78f38-龙耀路辅路.m4a",
        mode="offline", artifact="srt",
    )
    url = f"/api/tasks/{task_id}"
    assert client.get(url).json()["task"]["title"] == "1cd78f38-龙耀路辅路.m4a"
    store.set_summary(task_id, status="done", content={"title": "AI Skill 培训调整与报名推进"})
    task = client.get(url).json()["task"]
    assert task["title"] == "AI Skill 培训调整与报名推进"
    assert task["source_name"] == "1cd78f38-龙耀路辅路.m4a"
    assert client.get("/api/tasks").json()["tasks"][0]["title"] == task["title"]
    store.set_summary(task_id, content={"overview": "旧总结"})
    assert client.get(url).json()["task"]["title"] == task["source_name"]
