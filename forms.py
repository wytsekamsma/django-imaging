from django.forms.fields import ImageField

class ExtendedImageFormField(ImageField):
	def clean(self, data, initial=None):
		if data != '__deleted__':
			return super(ExtendedImageFormField, self).clean(data, initial)
		else:
			return '__deleted__'