Feature: Tasks repository get method testing

    Background: Initiate Platform Interface and create a project
        Given Platform Interface is initialized as dlp and Environment is set according to git branch
        And I create a project by the name of "tasks_get"
        And I create a dataset with a random name
        And There are items, path = "filters/image.jpg"
            |annotated_type={"box": 3, "polygon": 3}|metadata={"user.good": 3, "user.bad": 3}|

    @testrail-C4523169
    Scenario: Get - name
        When I create Task
            | task_name=min_params | due_date=auto | assignee_ids=auto |
        And I get task by "name"
        Then I receive a Task entity
        And Task received equals task created

    @testrail-C4523169
    Scenario: Get - id
        When I create Task
            | task_name=min_params | due_date=auto | assignee_ids=auto |
        And I get task by "id"
        Then I receive a Task entity
        And Task received equals task created

    @testrail-C4523169
    Scenario: Get - not existing - name
        When I create Task
            | task_name=min_params | due_date=auto | assignee_ids=auto |
        And I get task by wrong "name"
        Then "NotFound" exception should be raised

    @testrail-C4523169
    Scenario: Get - not existing - id
        When I create Task
            | task_name=min_params | due_date=auto | assignee_ids=auto |
        And I get task by wrong "id"
        Then "NotFound" exception should be raised
