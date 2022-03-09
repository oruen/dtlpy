import traceback
from typing import Union, List
import attr
import logging

from .. import repositories, entities, exceptions

logger = logging.getLogger(name='dtlpy')


class ItemAction:
    def __init__(self, action, display_name=None, color='#FFFFFF', icon=None):
        self.action = action
        self.display_name = display_name
        self.color = color
        self.icon = icon

    @classmethod
    def from_json(cls, _json: dict):
        kwarg = {
            'action': _json.get('action')
        }

        if _json.get('displayName', False):
            kwarg['display_name'] = _json['displayName']

        if _json.get('color', False):
            kwarg['color'] = _json['color']

        if _json.get('icon', False):
            kwarg['icon'] = _json['icon']

        return cls(**kwarg)

    def to_json(self) -> dict:
        _json = {
            'action': self.action,
            'color': self.color,
            'displayName': self.display_name if self.display_name is not None else self.action
        }

        if self.icon is not None:
            _json['icon'] = self.icon

        return _json


@attr.s
class Task:
    """
    Task object
    """

    # platform
    name = attr.ib()
    status = attr.ib()
    project_id = attr.ib()
    metadata = attr.ib(repr=False)
    id = attr.ib()
    url = attr.ib(repr=False)
    task_owner = attr.ib(repr=False)
    item_status = attr.ib(repr=False)
    creator = attr.ib()
    due_date = attr.ib()
    dataset_id = attr.ib()
    spec = attr.ib()
    recipe_id = attr.ib(repr=False)
    query = attr.ib(repr=False)
    assignmentIds = attr.ib(repr=False)
    annotation_status = attr.ib(repr=False)
    progress = attr.ib()
    for_review = attr.ib()
    issues = attr.ib()
    updated_at = attr.ib()
    created_at = attr.ib()
    available_actions = attr.ib()
    total_items = attr.ib()

    # sdk
    _client_api = attr.ib(repr=False)
    _current_assignments = attr.ib(default=None, repr=False)
    _assignments = attr.ib(default=None, repr=False)
    _project = attr.ib(default=None, repr=False)
    _dataset = attr.ib(default=None, repr=False)
    _tasks = attr.ib(default=None, repr=False)
    _settings = attr.ib(default=None, repr=False)

    @staticmethod
    def _protected_from_json(_json, client_api, project, dataset):
        """
        Same as from_json but with try-except to catch if error

        :param _json: platform json
        :param client_api: ApiClient entity
        :param project: project entity
        :param dataset: dataset entity
        :return:
        """
        try:
            task = Task.from_json(
                _json=_json,
                client_api=client_api,
                project=project,
                dataset=dataset
            )
            status = True
        except Exception:
            task = traceback.format_exc()
            status = False
        return status, task

    @classmethod
    def from_json(cls, _json, client_api, project=None, dataset=None):
        if project is not None:
            if project.id != _json.get('projectId', None):
                logger.warning('Task has been fetched from a project that is not belong to it')
                project = None

        if dataset is not None:
            if dataset.id != _json.get('datasetId', None):
                logger.warning('Task has been fetched from a dataset that is not belong to it')
                dataset = None

        actions = [ItemAction.from_json(_json=action) for action in _json.get('availableActions', list())]

        return cls(
            name=_json.get('name', None),
            status=_json.get('status', None),
            project_id=_json.get('projectId', None),
            metadata=_json.get('metadata', dict()),
            url=_json.get('url', None),
            spec=_json.get('spec', None),
            id=_json['id'],
            creator=_json.get('creator', None),
            due_date=_json.get('dueDate', 0),
            dataset_id=_json.get('datasetId', None),
            recipe_id=_json.get('recipeId', None),
            query=_json.get('query', None),
            task_owner=_json.get('taskOwner', None),
            item_status=_json.get('itemStatus', None),
            assignmentIds=_json.get('assignmentIds', list()),
            dataset=dataset,
            project=project,
            client_api=client_api,
            annotation_status=_json.get('annotationStatus', None),
            progress=_json.get('progress', None),
            for_review=_json.get('forReview', None),
            issues=_json.get('issues', None),
            updated_at=_json.get('updatedAt', None),
            created_at=_json.get('createdAt', None),
            available_actions=actions,
            total_items=_json.get('totalItems', None),
        )

    def to_json(self):
        """
        Returns platform _json format of object

        :return: platform json format of object
        :rtype: dict
        """
        _json = attr.asdict(
            self, filter=attr.filters.exclude(
                attr.fields(Task)._client_api,
                attr.fields(Task)._project,
                attr.fields(Task).project_id,
                attr.fields(Task).dataset_id,
                attr.fields(Task).recipe_id,
                attr.fields(Task).task_owner,
                attr.fields(Task).available_actions,
                attr.fields(Task).item_status,
                attr.fields(Task).due_date,
                attr.fields(Task)._tasks,
                attr.fields(Task)._dataset,
                attr.fields(Task)._current_assignments,
                attr.fields(Task)._assignments,
                attr.fields(Task).annotation_status,
                attr.fields(Task).for_review,
                attr.fields(Task).issues,
                attr.fields(Task).updated_at,
                attr.fields(Task).created_at,
                attr.fields(Task).total_items,
                attr.fields(Task)._settings,
            )
        )
        _json['projectId'] = self.project_id
        _json['datasetId'] = self.dataset_id
        _json['recipeId'] = self.recipe_id
        _json['taskOwner'] = self.task_owner
        _json['dueDate'] = self.due_date
        _json['totalItems'] = self.total_items
        _json['forReview'] = self.for_review

        if self.available_actions is not None:
            _json['availableActions'] = [action.to_json() for action in self.available_actions]

        return _json

    @property
    def platform_url(self):
        return self._client_api._get_resource_url("projects/{}/tasks/{}".format(self.project.id, self.id))

    @property
    def current_assignments(self):
        if self._current_assignments is None:
            self._current_assignments = list()
            for assignment in self.assignmentIds:
                self._current_assignments.append(self.assignments.get(assignment_id=assignment))
        return self._current_assignments

    @property
    def assignments(self):
        if self._assignments is None:
            self._assignments = repositories.Assignments(client_api=self._client_api, dataset=self._dataset,
                                                         project=self.project, task=self, project_id=self.project_id)
        assert isinstance(self._assignments, repositories.Assignments)
        return self._assignments

    @property
    def tasks(self):
        if self._tasks is None:
            self._tasks = repositories.Tasks(client_api=self._client_api, project=self.project, dataset=self.dataset)
        assert isinstance(self._tasks, repositories.Tasks)
        return self._tasks

    @property
    def settings(self):
        if self._settings is None:
            self._settings = repositories.Settings(
                client_api=self._client_api,
                project=self.project,
                dataset=self.dataset,
                task=self
            )
        assert isinstance(self._settings, repositories.Settings)
        return self._settings

    @property
    def project(self):
        if self._project is None:
            self.get_project()
            if self._project is None:
                raise exceptions.PlatformException(error='2001',
                                                   message='Missing entity "project". need to "get_project()" ')
        assert isinstance(self._project, entities.Project)
        return self._project

    @property
    def dataset(self):
        if self._dataset is None:
            self.get_dataset()
            if self._dataset is None:
                raise exceptions.PlatformException(error='2001',
                                                   message='Missing entity "dataset". need to "get_dataset()" ')
        assert isinstance(self._dataset, entities.Dataset)
        return self._dataset

    def get_project(self):
        if self._project is None:
            self._project = repositories.Projects(client_api=self._client_api).get(project_id=self.project_id)

    def get_dataset(self):
        if self._dataset is None:
            self._dataset = repositories.Datasets(client_api=self._client_api, project=self._project).get(
                dataset_id=self.dataset_id)

    def open_in_web(self):
        """
        Open the task in web platform

        :return:
        """
        self._client_api._open_in_web(url=self.platform_url)

    def delete(self, wait=True):
        """
        Delete task from platform

        :param wait: wait for the command to finish
        :return: True
        """
        return self.tasks.delete(task_id=self.id, wait=wait)

    def update(self, system_metadata=False):
        """
        Update an Annotation Task

        :param system_metadata: True, if you want to change metadata system
        """
        return self.tasks.update(task=self, system_metadata=system_metadata)

    def create_qa_task(self,
                       due_date,
                       assignee_ids,
                       filters=None,
                       items=None,
                       query=None,
                       workload=None,
                       metadata=None,
                       available_actions=None,
                       wait=True,
                       ):
        """
        Create a new QA Task

        :param float due_date: date to when finish the task
        :param list assignee_ids: list of assignee
        :param entities.Filters filters: filter to the task
        :param List[entities.Item] items: item to insert to the task
        :param entities.Filters query: filter to the task
        :param List[WorkloadUnit] workload: list WorkloadUnit for the task assignee
        :param dict metadata: metadata for the task
        :param list available_actions: list of available actions to the task
        :param bool wait: wait for the command to finish
        :return: task object
        :rtype: dtlpy.entities.task.Task
        """
        return self.tasks.create_qa_task(task=self,
                                         due_date=due_date,
                                         assignee_ids=assignee_ids,
                                         filters=filters,
                                         items=items,
                                         query=query,
                                         workload=workload,
                                         metadata=metadata,
                                         available_actions=available_actions,
                                         wait=wait,
                                         )

    def create_assignment(self, assignment_name, assignee_id, items=None, filters=None):
        """
        Create a new assignment

        :param assignment_name: assignment name
        :param assignee_id: list of assignee for the assignment
        :param items: items list for the assignment
        :param dtlpy.entities.filters.Filters filters: Filters entity or a dictionary containing filters parameters
        :return:
        """
        assignment = self.assignments.create(assignee_id=assignee_id,
                                             filters=filters,
                                             items=items)

        assignment.metadata['system']['taskId'] = self.id
        assignment.update(system_metadata=True)
        self.assignmentIds.append(assignment.id)
        self.update()
        self.add_items(filters=filters, items=items)
        return assignment

    def add_items(self, filters=None, items=None, assignee_ids=None, workload=None, limit=0, wait=True):
        """
        Add items to Task

        :param dtlpy.entities.filters.Filters filters: Filters entity or a dictionary containing filters parameters
        :param items: items list for the assignment
        :param assignee_ids: list of assignee for the assignment
        :param workload: the load of work
        :param limit: limit
        :param wait: wait for the command to finish
        :return:
        """
        return self.tasks.add_items(task=self,
                                    filters=filters,
                                    items=items,
                                    assignee_ids=assignee_ids,
                                    workload=workload,
                                    limit=limit,
                                    wait=wait)

    def get_items(self, filters=None):
        """
        Get the task items

        :param dtlpy.entities.filters.Filters filters: Filters entity or a dictionary containing filters parameters
        :return:
        """
        return self.tasks.get_items(task_id=self.id, dataset=self.dataset, filters=filters)

    def set_status(self, status: str, operation: str, item_ids: List[str]):
        """
        Update item status within task

        :param status: str - string the describes the status
        :param operation: str -  'create' or 'delete'
        :param item_ids: List[str]

        :return : Boolean

        """
        return self.tasks.set_status(status=status, operation=operation, item_ids=item_ids, task_id=self.id)
