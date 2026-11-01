from django.shortcuts import render
from django.http import HttpResponseRedirect, HttpResponseForbidden
from .models import Course, Enrollment, Question, Choice, Submission
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
import logging

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}
    if request.method == 'GET':
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)
    elif request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']
        user_exist = User.objects.filter(username=username).exists()
        if not user_exist:
            user = User.objects.create_user(
                username=username, first_name=first_name,
                last_name=last_name, password=password
            )
            login(request, user)
            return redirect("onlinecourse:index")
        context['message'] = "User already exists."
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)


def login_request(request):
    context = {}
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')
        context['message'] = "Invalid username or password."
    return render(request, 'onlinecourse/user_login_bootstrap.html', context)


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    if not user.is_authenticated:
        return False
    return Enrollment.objects.filter(user=user, course=course).exists()


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]
        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)
        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user
    if user.is_authenticated and not check_if_enrolled(user, course):
        Enrollment.objects.create(user=user, course=course, mode='honor')
        course.total_enrollment += 1
        course.save()
    return HttpResponseRedirect(reverse('onlinecourse:course_details', args=(course.id,)))


def extract_answers(request):
    submitted_answers = []
    for key in request.POST:
        if key.startswith('choice'):
            try:
                submitted_answers.append(int(request.POST[key]))
            except (TypeError, ValueError):
                continue
    return submitted_answers


def submit(request, course_id):
    """Save a learner's selected answers and redirect to the result page."""
    if request.method != 'POST':
        return HttpResponseRedirect(reverse('onlinecourse:course_details', args=(course_id,)))
    if not request.user.is_authenticated:
        return HttpResponseForbidden("Please log in before submitting an exam.")

    course = get_object_or_404(Course, pk=course_id)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)
    submission = Submission.objects.create(enrollment=enrollment)

    selected_choice_ids = extract_answers(request)
    valid_choices = Choice.objects.filter(
        id__in=selected_choice_ids, question__course=course
    )
    submission.choices.set(valid_choices)

    return HttpResponseRedirect(reverse(
        'onlinecourse:show_exam_result',
        args=(course.id, submission.id)
    ))


def show_exam_result(request, course_id, submission_id):
    """Calculate the score and render per-question feedback for a submission."""
    if not request.user.is_authenticated:
        return HttpResponseForbidden("Please log in to view exam results.")

    course = get_object_or_404(Course, pk=course_id)
    submission = get_object_or_404(
        Submission, pk=submission_id, enrollment__course=course,
        enrollment__user=request.user
    )
    selected_ids = list(submission.choices.values_list('id', flat=True))

    total_score = 0
    max_score = 0
    question_results = []

    for question in course.question_set.all():
        max_score += question.grade
        choices = list(question.choice_set.all())
        selected_for_question = [
            choice for choice in choices if choice.id in selected_ids
        ]
        correct_choices = [choice for choice in choices if choice.is_correct]
        is_correct = question.is_get_score(selected_ids)
        if is_correct:
            total_score += question.grade

        question_results.append({
            'question': question,
            'choices': choices,
            'selected_choices': selected_for_question,
            'correct_choices': correct_choices,
            'is_correct': is_correct,
        })

    grade = (total_score / max_score * 100) if max_score else 0
    context = {
        'course': course,
        'submission': submission,
        'grade': grade,
        'total_score': total_score,
        'max_score': max_score,
        'question_results': question_results,
    }
    return render(request, 'onlinecourse/exam_result_bootstrap.html', context)
