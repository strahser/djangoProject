from collections import defaultdict

from django.db import migrations


TASK_FIELDS = [
    'owner_id', 'project_site_id', 'sub_project_id', 'building_number_id',
    'name', 'description', 'design_chapter_id', 'contractor_id',
    'status_id', 'category_id', 'price', 'contract_id', 'due_date',
    'creation_stamp', 'update_stamp',
]


def forward(apps, schema_editor):
    Task = apps.get_model('ProjectTDL', 'Task')
    SubTask = apps.get_model('ProjectTDL', 'SubTask')
    TaskNode = apps.get_model('ProjectTDL', 'TaskNode')

    # --- 1. Root tasks (node_type='task', no parent) ---
    root_nodes = []
    tree_id = 1
    for task in Task.objects.all().iterator():
        kwargs = {f: getattr(task, f) for f in TASK_FIELDS}
        root_nodes.append(TaskNode(
            id=task.pk,  # reuse old PK so subtask FK still works
            node_type='task', parent=None,
            lft=1, rght=2, tree_id=tree_id, level=0,
            **kwargs,
        ))
        tree_id += 1

    TaskNode.objects.bulk_create(root_nodes)

    # --- 2. Subtask as children ---
    # Group subtasks by parent to assign sequential lft/rght
    children_by_parent = defaultdict(list)
    for st in SubTask.objects.all().iterator():
        children_by_parent[st.parent_id].append(st)

    child_nodes = []
    for parent_pk, subtasks in children_by_parent.items():
        parent_node = TaskNode.objects.get(pk=parent_pk)
        for idx, st in enumerate(subtasks):
            child_nodes.append(TaskNode(
                node_type='subtask',
                parent=parent_node,
                owner=parent_node.owner,
                project_site=parent_node.project_site,
                sub_project=parent_node.sub_project,
                name=st.name or '',
                description=st.description,
                price=st.price,
                due_date=st.due_date,
                creation_stamp=st.creation_stamp,
                update_stamp=st.update_stamp,
                lft=2 + idx * 2,
                rght=3 + idx * 2,
                tree_id=parent_node.tree_id,
                level=1,
            ))

        # Update parent's rght to encompass children
        TaskNode.objects.filter(pk=parent_pk).update(
            rght=1 + len(subtasks) * 2
        )

    if child_nodes:
        TaskNode.objects.bulk_create(child_nodes)


def backward(apps, schema_editor):
    TaskNode = apps.get_model('ProjectTDL', 'TaskNode')
    TaskNode.objects.filter(node_type__in=('task', 'subtask')).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ProjectTDL', '0003_remove_tasknode_emails'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
