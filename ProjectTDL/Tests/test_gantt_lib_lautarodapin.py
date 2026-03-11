import gantt_lib
import datetime

resource = gantt_lib.Resource("Resource 1")

project = gantt_lib.HiperLinkedProject(
    name='Project',
    link='mypage/link/to/project',
    target='_self'  # HTML target (it opens the link on the same page)
)

project.add_task(gantt_lib.HyperLinkedTask(
    name='task 1',
    start=datetime.date(2020, 7, 1),
    duration=5,
    resources=[resource],
    percent_done=0,
    color="#03d529",
    link_name='mypage/link/to/title',
    link_resource='mypage/link/to/resource',
    link_lateral='mypage/link/to/extra',
    target='_self'  # HTML target (it opens the link on the same page)
)
)

# make_svg_for_task returns the xml code in string format, this way you can use it as context in django or flask
# also saves it into a file
svg = project.make_svg_for_tasks(
    'file.svg',
    today=datetime.date(2020, 7, 15),
    start=datetime.date(2020, 7, 1),
    end=datetime.date(2020, 7, 20)
)

# Or you can get only the svg (str) code
svg_string = project.get_string_svg_for_tasks(
    today=datetime.date(2020, 7, 15),
    start=datetime.date(2020, 7, 1),
    end=datetime.date(2020, 7, 20)
)
