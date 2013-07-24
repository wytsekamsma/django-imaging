from django.db import models
from django.db.models import signals
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os, shutil
from forms import ExtendedImageFormField
from widgets import DelAdminFileWidget

class ResizedImageField:
	def __init__(self, name):
		self.name = name
		self.storage = FileSystemStorage()
		
	def path(self):
		return self.storage.path(self.name)
		
	def url(self):
		return self.storage.url(self.name)
		
	def size(self):
		return self.storage.size(self.name)
			
class ExtendedImageField(models.ImageField):
	def __init__(self, verbose_name=None, name=None, width_field=None, height_field=None, sizes=None, **kwargs):
		"""
			Added fields:
				- sizes: a tuple like this:
					* ("default", 640, 480, True) > resize to 640x480px, crop to fill frame (filename=image01_default.jpg)
					* (640, 0) > resize to 640px wide (cropping has no effect)				(filename=image01_640.jpg)
					* (0, 480) > resize to 480px high (cropping has no effect)				(filename=image01_480.jpg)
					* (640, 480, False) > resize to 640x480px, don't crop					(filename=image01_640x480.jpg	
					
			image.url -> uploaded size
			image.default.url -> "default" size
			image.640x480.url ->
			etc
		"""
		self.sizes = self._parse_sizes(sizes)
				
		super(ExtendedImageField, self).__init__(verbose_name, name, width_field, height_field, **kwargs)		
			
	def _resize_image(self, filename, size):
		"""
		Resizes the image to specified width, height and force option
			- filename: full path of image to resize
			- size: dictionary containing:
				- width: new width
				- height: new height
				- force: if True, image will be cropped to fit the exact size,
					if False, it will have the bigger size that fits the specified
					size, but without cropping, so it could be smaller on width or height
		"""
		WIDTH, HEIGHT = 0, 1
		from PIL import Image, ImageOps
		img = Image.open(filename)
		if img.size[WIDTH] > size['width'] or img.size[HEIGHT] > size['height']:
			if size['crop']:
				img = ImageOps.fit(img, (size['width'], size['height']), Image.ANTIALIAS)
			elif size['width'] is 0 or size['height'] is 0:
				if size['width'] is 0:
					size['width'] = int(round(float(img.size[WIDTH]) / float((img.size[HEIGHT])/float(size['height']))))
				else:
					size['height'] = int(round(float(img.size[HEIGHT]) / float((img.size[WIDTH])/float(size['width']))))
				img.thumbnail((size['width'], size['height']), Image.ANTIALIAS)
			else:
				img.thumbnail((size['width'], size['height']), Image.ANTIALIAS)
		try:
			img.save(filename, optimize=1)
		except IOError:
			img.save(filename)	
			
	def _rename_resize_image(self, instance=None, **kwargs):
		"""
		Renames the image, and calls the method to resize
		"""
		if getattr(instance, self.name):
			src = getattr(instance, self.name).path
			filename, ext = os.path.splitext(os.path.basename(src))
			if self.sizes:
				for size in self.sizes:
					dst = self.generate_filename(instance, '%s_%s%s' % (filename, size['name'], ext)) ## 	dst==filename
					dst_fullpath = os.path.join(settings.MEDIA_ROOT, dst)
					shutil.copyfile(src, dst_fullpath)
					self._resize_image(dst_fullpath, size)
			
	def _set_resized_image(self, instance=None, **kwargs):
		if getattr(instance, self.name):
			src = getattr(instance, self.name).path
			filename, ext = os.path.splitext(os.path.basename(src))
			if self.sizes:
				for size in self.sizes:
					_filename = self.generate_filename(instance, '%s_%s%s' % (filename, size['name'], ext))
					resized_image_field = ResizedImageField(_filename)
					setattr(getattr(instance, self.name), "size_%s" % size['name'], resized_image_field)		
					
	def _parse_sizes(self, sizes):
		if sizes:
			_sizes = []
		
			if not isinstance(sizes[0], tuple):
				sizes = (sizes, )
				
			for size in sizes:
				_name = None
				_width = None
				_height = None
				_crop = True
				
				if type(size[0]) is str:
					## named size
					_name = size[0]
					_width = size[1]
					_height = size[2]
				
					if len(size) is 4:
						_crop = size[3]
						if _width is 0 or _height is 0:
							_crop = False
				
				elif((type(size[0]) is int) and (type(size[1]) is int)):
					## unnamed size
					_width = size[0]
					_height = size[1]
					if len(size) is 3:
						_crop = size[2]
		
					if((size[0] is not 0) and (size[1] is not 0)):
						_name = "%sx%s" % (size[0], size[1])
					elif size[0] is 0:
						_name = "%s" % size[1]
						_crop = False
					else:
						_name = "%s" % size[0]
						_crop = False
						
				_sizes.append(
					{
						'name':_name,
						'width':_width,
						'height':_height,
						'crop':_crop
					}
				)
			if len(_sizes) is not 0:
				return _sizes
			return None
		return None
		
	def formfield(self, **kwargs):
		kwargs['widget'] = DelAdminFileWidget
		kwargs['form_class'] = ExtendedImageFormField
		return super(ExtendedImageField, self).formfield(**kwargs)	
			
	def save_form_data(self, instance, data):
		if data == '__deleted__':
			filename = getattr(instance, self.name).path
			ext = os.path.splitext(filename)[1].lower().replace('jpg', 'jpeg')
	
			if os.path.exists(filename):
				os.remove(filename)
			setattr(instance, self.name, None)
				
			if self.sizes:
				for size in self.sizes:
					src = self.generate_filename(instance, '%s_%s%s' % (self.name, size['name'], ext))
					src_fullpath = os.path.join(settings.MEDIA_ROOT, src)
					
					if os.path.exists(src_fullpath):
						os.remove(src_fullpath)
		else:
			super(ExtendedImageField, self).save_form_data(instance, data)
						
	def get_db_prep_save(self, value):
		if value:
			return super(ExtendedImageField, self).get_db_prep_save(value, connection=connection)
		else:
			return u''
	
	def contribute_to_class(self, cls, name):
		super(ExtendedImageField, self).contribute_to_class(cls, name)
		signals.post_save.connect(self._rename_resize_image, sender=cls)
		signals.post_init.connect(self._set_resized_image, sender=cls)

from south.modelsinspector import add_introspection_rules
add_introspection_rules([], ["^imaging\.fields\.ExtendedImageField"])
