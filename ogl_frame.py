from tkinter import *
from OpenGL import GL

import numpy
import ctypes
import types
import sys
from pyopengltk import OpenGLFrame
from ogl_objects import *
from ogl_fbo import FBO
import ogl_shader
if sys.version_info[0] > 2:
	import tkinter as tk
else:
	import Tkinter as tk


PRIMITIVE_RESTART = 65536204;


def magnitude(v):
	return numpy.sqrt(numpy.sum(v ** 2))


def normalize(v):
	m = magnitude(v)
	if m == 0:
		return v
	return v / m
					
					
def translate(xyz):
	x, y, z = xyz
	return numpy.matrix([[1,0,0,x],
					  [0,1,0,y],
					  [0,0,1,z],
					  [0,0,0,1]])
			
			
def normal_from_polar(lat, long):
	x = numpy.cos(lat) * numpy.sin(long)
	y = numpy.sin(lat) * numpy.sin(long)
	z = numpy.cos(long)
	return -numpy.array((x, y, z))


def viewPolar( f, s, u, eye ):
	M = numpy.matrix(numpy.identity(4))
	M[:3,:3] = numpy.vstack([f, s, u])
	T = translate(-numpy.array(eye))
	return M * T


class AppOgl(OpenGLFrame):
	button_center = (0, 0)
	origin = numpy.array([0., 0., 0.])
	rotation = [0, 0, numpy.deg2rad(90), 0]
	forward_vec = numpy.array([0., 0., 0.])
	right_vec = numpy.array([0., 0., 0.])
	up_vec = numpy.array([0., 0., 0.])
	
	render_fbo = None
	pick_fbo = None
	
	opengl_meshes = {}
	opengl_objects = []
	
	def initgl(self):
		GL.glClearColor(0.15, 0.15, 0.15, 1.0)
		
		GL.glDepthFunc(GL.GL_LEQUAL)
		GL.glEnable(GL.GL_DEPTH_TEST)
		
		GL.glEnable(GL.GL_PROGRAM_POINT_SIZE)
		if not hasattr(self, "shaders"):
			self.shaders = {}
			for shader_name, vertex_shader, fragment_shader in ogl_shader.SHADER_LIST:
				self.shaders[shader_name] = ogl_shader.SHADER(vertex_shader, fragment_shader)
		
		GL.glEnable(GL.GL_CULL_FACE)
		GL.glCullFace(GL.GL_FRONT)
		
		GL.glEnable(GL.GL_PRIMITIVE_RESTART)
		GL.glPrimitiveRestartIndex(PRIMITIVE_RESTART)
		
		if self.render_fbo is not None:
			if self.width != self.render_fbo.width or self.height != self.render_fbo.height:
				del self.render_fbo
				self.render_fbo = FBO(self.width, self.height, 4)
				self.pick_fbo = FBO(self.width, self.height, 0)
		else:
			self.render_fbo = FBO(self.width, self.height, 4)
			self.pick_fbo = FBO(self.width, self.height, 0)

		self.is_picking = False
		
	def redraw(self):
		if self.render_fbo is None:
			self.render_fbo = FBO(self.width, self.height, 4)


		shader = self.shaders["Vertex_Color"]
		fbo = self.render_fbo.bind
		if self.is_picking:
			fbo = self.pick_fbo.bind
			shader = self.shaders["Pick_Object"]
			
		GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
		GL.glUseProgram(shader.program)
		#clear buffer
		GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
		self.set_view(shader)
		self.set_projection(shader, 100.0)
		
		GL.glDisable(GL.GL_BLEND)
		GL.glEnable(GL.GL_CULL_FACE)
		GL.glDepthMask (GL.GL_TRUE)
		current_blend = None
		
		for obj in self.opengl_objects:
			if obj.hidden:
				continue
				
			if obj.mesh.blend and current_blend is None:
				if not self.is_picking:
					GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE)
					GL.glEnable(GL.GL_BLEND)
					GL.glDepthMask (GL.GL_FALSE)
					
				GL.glDisable(GL.GL_CULL_FACE)
				current_blend = obj.mesh.blend
			elif obj.mesh.blend is None and current_blend is not None:
				GL.glDisable(GL.GL_BLEND)
				GL.glEnable(GL.GL_CULL_FACE)
				GL.glDepthMask (GL.GL_TRUE)
				current_blend = obj.mesh.blend
				
			GL.glUniformMatrix4fv(shader.uniform_loc["u_model_mat"], 1, GL.GL_FALSE, obj.modelMatrix)
			if (shader.uniform_loc["u_line"] != -1):
				GL.glUniform4f(shader.uniform_loc["u_line"], *obj.encoded_object_index);
			
			if obj.selected and not self.is_picking:
				GL.glUniform4f(shader.uniform_loc["u_color"], 1., .01, 1., 1.);
				obj.draw()
				GL.glUniform4f(shader.uniform_loc["u_color"], 1., 1., 1., 0.);
			else:
				obj.draw()

		GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
		GL.glBindVertexArray(0)
		GL.glUseProgram(0)
		GL.glRasterPos2f(-0.99, -0.99)
		GL.glDisable(GL.GL_BLEND)
		GL.glEnable(GL.GL_CULL_FACE)
		GL.glDepthMask (GL.GL_TRUE)
		
		if not self.is_picking:
			GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER, 0);
			GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, self.render_fbo.bind);
			GL.glDrawBuffer(GL.GL_BACK);
			GL.glBlitFramebuffer(0, 0, self.width, self.height, 0, 0, self.width, self.height, GL.GL_COLOR_BUFFER_BIT, GL.GL_NEAREST)
		
		self.is_picking = False
		
	def get_current_ent_line(self, x, y):
		self.is_picking = True
		
		self.redraw()
		
		GL.glFlush()
		GL.glFinish()
		
		GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.pick_fbo.bind)
		GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, self.pick_fbo.bind)
		GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER, self.pick_fbo.bind)
		
		GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT0)
		data = GL.glReadPixels(x, self.height - y, 1, 1, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
		GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT0)
		
		GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, 0)
		GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER, 0)
		GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
		
		picked_object_index = data[0] + data[1] * 256 + data[2] * 256*256;
		try:
			picked_line = self.opengl_objects[picked_object_index].new_line
		except:
			return
		
		self.text.tag_remove("found", '1.0', END)
		idx = self.text.search("}", str(picked_line + 1)+".0", nocase=0, stopindex=END)
		try:
			line, char = idx.split(".")
		except:
			return
		self.text.tag_add('found', str(picked_line + 1)+".0", str(int(line)+1)+"."+char)
		self.text.tag_config('found', foreground='white', background='green')
		self.text.see(str(picked_line + 1)+".0")
		
		self.unselect_all()
		self.opengl_objects[picked_object_index].selected = True

	def unselect_all(self, *args):
		for obj in self.opengl_objects:
			obj.selected = False
			
	def hide_selected(self, *args):
		for obj in self.opengl_objects:
			if obj.selected:
				obj.hidden = True
				
	def unhide_all(self, *args):
		for obj in self.opengl_objects:
			obj.hidden = False

	def set_view(self, shader):
		F = normal_from_polar(self.rotation[1], self.rotation[2])
		self.forward_vec = normalize(F)
		U = (0.0, 0.0, 1.0)
		self.right_vec = normalize(numpy.cross(self.forward_vec, U))
		self.up_vec = numpy.cross(self.right_vec, self.forward_vec)
		v = viewPolar(
			self.forward_vec,
			self.right_vec,
			self.up_vec,
			self.origin)
		GL.glUniformMatrix4fv(shader.uniform_loc["u_view_mat"], 1, GL.GL_FALSE, numpy.transpose(v))


	def set_projection(self, shader, fov_y):
		znear = 4.
		zfar = 40000.
		depth = zfar - znear
		height = 2.0 * (znear * numpy.tan(numpy.radians(0.5 * fov_y)))
		width = height * self.width / self.height
		
		p = numpy.array(
			(
				(0., 2.0 * znear / width, 0, 0),
				(0., 0, 2.0 * znear / height, 0),
				((zfar + znear) / depth, 0, 0, (-2.0 * zfar * znear) / depth),
				(1., 0, 0, 0)
			),
			numpy.float32
		)
		GL.glUniformMatrix4fv(shader.uniform_loc["u_proj_mat"], 1, GL.GL_FALSE, numpy.transpose(p))


	def add_bsp_object(self, name, bsp_object):
		if bsp_object is None:
			return
		mesh = None
		if bsp_object.mesh_name == "worldspawn":
			mesh = self.opengl_meshes.get("*0")
			print(mesh, "*0")
		else:
			mesh = self.opengl_meshes.get(
				bsp_object.mesh_name)
			print(mesh, bsp_object.mesh_name)
			
		if mesh is None:
			print(bsp_object.name)
			new_mesh_name = ""
			colors = None
			if bsp_object.name.startswith("info_n") or bsp_object.name.startswith("light"):
				new_mesh_name = "box_green"
				colors = green_box_colors
			elif bsp_object.name.startswith("ammo") or bsp_object.name.startswith("holocron"):
				new_mesh_name = "box_cyan"
				colors = cyan_box_colors
			elif (
				 bsp_object.name.startswith("misc_") or
				 bsp_object.name.startswith("emplaced_") or
				 bsp_object.name.startswith("fx_")):
				new_mesh_name = "box_blue"
				colors = blue_box_colors
			else:
				new_mesh_name = "box_red"
				colors = red_box_colors
			
			mesh = self.opengl_meshes.get(new_mesh_name)
			if mesh is None:
				self.add_bsp_mesh(new_mesh_name, box_verts, box_indices, colors, box_normals)
				mesh = self.opengl_meshes.get(new_mesh_name)
			
		if bsp_object.mesh_name is not None and bsp_object.mesh_name.startswith("*"):
			rotation = numpy.array((0.0, 0.0, 0.0))
		else:
			rotation = bsp_object.rotation

		new_object = OpenGLObject(
			mesh,
			bsp_object.position,
			rotation,
			bsp_object.scale
			)
		new_object.new_line = int(bsp_object.custom_parameters["first_line"])
		
		object_index = len(self.opengl_objects)
		r = (object_index & 0x000000FF) >>  0;
		g = (object_index & 0x0000FF00) >>  8;
		b = (object_index & 0x00FF0000) >> 16;
		new_object.encoded_object_index = float(r)/255.0, float(g)/255.0, float(b)/255.0, 0.0
		
		self.opengl_objects.append(new_object)
		
	def add_bsp_mesh(self, name, vertices, indices=None, colors=None, normals = None, blend = None, tc0=None, tc1=None):
		new_indices = []
		
		mode = GL.GL_TRIANGLES
		for surface in indices:
			if len(surface) > 4:
				mode = GL.GL_TRIANGLE_FAN
		for surface in indices:
			if len(surface) == 4 and mode != GL.GL_TRIANGLE_FAN:
				new_indices.append(surface[0])
				new_indices.append(surface[2])
				new_indices.append(surface[1])
				
				new_indices.append(surface[2])
				new_indices.append(surface[0])
				new_indices.append(surface[3])
				continue
			for index in surface:
				new_indices.append(index)
			if mode == GL.GL_TRIANGLE_FAN:
				new_indices.append(PRIMITIVE_RESTART)

		new_positions = []
		for vert in vertices:
			new_positions.append(vert[0])
			new_positions.append(vert[1])
			new_positions.append(vert[2])
		new_colors = []
		for color in colors:
			if (color[0] + color[1] + color[2]) < 30:
				new_colors.append(color[0] + 30)
				new_colors.append(color[1] + 30)
				new_colors.append(color[2] + 30)
				new_colors.append(color[3])
				continue
			new_colors.append(color[0])
			new_colors.append(color[1])
			new_colors.append(color[2])
			new_colors.append(color[3])
		new_normals = []
		for normal in normals:
			new_normals.append(normal[0])
			new_normals.append(normal[1])
			new_normals.append(normal[2])

		self.opengl_meshes[name] = (
			OpenGLMesh(
				numpy.array(new_positions).astype(numpy.float32),
				numpy.array(new_indices).astype(numpy.uint32),
				numpy.array(new_colors).astype(numpy.uint8),
				numpy.array(new_normals).astype(numpy.float32),
				blend
				)
			)
		self.opengl_meshes[name].render_type = mode
		
	def clear_objects(self):
		self.opengl_objects.clear()	
	
	def clear_meshes(self):
		self.opengl_meshes.clear()
		
	def __del__(self):
		self.opengl_objects.clear()  
		self.opengl_meshes.clear()
		
	def append(self, text):
		self.text = text
		
def move_fwd(event):
	event.widget.origin += 120. * event.widget.forward_vec
	
def move_lft(event):
	event.widget.origin -= 120. * event.widget.right_vec
	
def move_rgt(event):
	event.widget.origin += 120. * event.widget.right_vec
	
def move_bck(event):
	event.widget.origin -= 120. * event.widget.forward_vec
   
def move_up(event):
	event.widget.origin += 120. * numpy.array((0.0, 0.0, 1.0))
	
def move_down(event):
	event.widget.origin -= 120. * numpy.array((0.0, 0.0, 1.0))
	
def m1click(event):
	event.widget.get_current_ent_line(event.x, event.y)

def m3click(event):
	event.widget.button_center = (event.x, event.y)
		
def m3drag(event):
	event.widget.rotation = [
		1.0,
		event.widget.rotation[1] + (-event.widget.button_center[0] + event.x) * 0.003,
		event.widget.rotation[2] + (-event.widget.button_center[1] + event.y) * 0.003,
		0]
	event.widget.rotation[2] = min(event.widget.rotation[2], numpy.deg2rad(185.0))
	event.widget.rotation[2] = max(event.widget.rotation[2], numpy.deg2rad(5.0))
	event.widget.button_center = (event.x, event.y)
	
def mwheel(event):
	event.widget.origin += event.delta * 0.5 * event.widget.forward_vec

def main(root, text):
	app = AppOgl(root, width = 2000, height = 400)
	app.animate = 1 #1000 // 60
	app.after(200, app.printContext)
	app.append(text)
	
	app.bind("w", move_fwd)
	app.bind("s", move_bck)
	app.bind("a", move_lft)
	app.bind("d", move_rgt)
	app.bind("h", app.hide_selected)
	root.bind_all("<Alt-h>", app.unhide_all)
	app.bind("<space>", move_up)
	app.bind("c", move_down)
	app.bind("<B3-Motion>", m3drag)
	app.bind("<Button-3>", m3click)
	app.bind("<Button-1>", m1click)
	app.bind("<MouseWheel>", mwheel)
	app.bind('<Escape>', app.unselect_all)
	return app

if __name__ == "__main__":
	print("Please run 'main.py'")