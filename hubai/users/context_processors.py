from django.conf import settings


def legal(request):
    return {"delete_all_data_on": settings.DELETE_ALL_DATA_ON, "data_contact": settings.DATA_CONTACT}
