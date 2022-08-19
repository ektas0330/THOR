#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author: Ekta Samani
"""

import numpy as np
import time
import cv2,os,csv

from math import pi, sin, cos
from direct.showbase.ShowBase import ShowBase
from panda3d.core import FrameBufferProperties, WindowProperties
from panda3d.core import GraphicsPipe, GraphicsOutput
from panda3d.core import Texture
from panda3d.core import loadPrcFileData

from direct.task import Task
from direct.actor.Actor import Actor
from direct.interval.IntervalGlobal import Sequence
from panda3d.core import Point3
from panda3d.core import AmbientLight, DirectionalLight, PointLight, Filename, Lens, MatrixLens, LMatrix4f, VBase4, Material, loadPrcFileData

loadPrcFileData('', 'show-frame-rate-meter true')
loadPrcFileData('', 'sync-video 0')


def show_rgbd_image(image, depth_image, window_name='Image window', delay=1, depth_offset=0.0, depth_scale=1.0):
    if depth_image.dtype != np.uint8:
        if depth_scale is None:
            depth_scale = depth_image.max() - depth_image.min()

        if depth_offset is None:
            depth_offset = depth_image.min()

        depth_image = np.clip((depth_image - depth_offset) / depth_scale, 0.0, 1.0)
        depth_image = (255.0 * depth_image).astype(np.uint8)
    depth_image = np.tile(depth_image, (1, 1, 3))
    if image.shape[2] == 4:  # add alpha channel
        alpha = np.full(depth_image.shape[:2] + (1,), 255, dtype=np.uint8)
        depth_image = np.concatenate([depth_image, alpha], axis=-1)
    images = np.concatenate([image, depth_image], axis=1)
    cv2.imshow(window_name, images)
    key = cv2.waitKey(delay)
    key &= 255
    if key == 27 or key == ord('q'):
        print("Pressed ESC or q, exiting")
        exit_request = True
    else:
        exit_request = False
    return exit_request

def save_rgbd_image(image, depth_image, datadir, filename, depth_offset, depth_scale):
    if depth_image.dtype != np.uint8:
        np.save(datadir+'depth/'+os.path.splitext(filename)[0]+'.npy', depth_image)

        if depth_scale is None:
            depth_scale = depth_image.max() - depth_image.min()

        if depth_offset is None:
            depth_offset = depth_image.min()

        depth_image = np.clip((depth_image - depth_offset) / depth_scale, 0.0, 1.0)
        
        depth_image = (255.0 * depth_image).astype(np.uint8)
    depth_image = np.tile(depth_image, (1, 1, 3))

    cv2.imwrite(datadir+'depth/'+filename, depth_image)
    cv2.imwrite(datadir+'rgb/'+filename, image)



def Rz_yaw(yaw):
    Rz_yaw = np.array([
        [np.cos(yaw), -np.sin(yaw), 0],
        [np.sin(yaw),  np.cos(yaw), 0],
        [          0,            0, 1]])
    return Rz_yaw

def Ry_pitch(pitch):
    Ry_pitch = np.array([
        [ np.cos(pitch), 0, np.sin(pitch)],
        [             0, 1,             0],
        [-np.sin(pitch), 0, np.cos(pitch)]])
    return Ry_pitch

def Rx_roll(roll):
    Rx_roll = np.array([
        [1,            0,             0],
        [0, np.cos(roll), -np.sin(roll)],
        [0, np.sin(roll),  np.cos(roll)]])
    return Rx_roll


class MyApp(ShowBase):
    def __init__(self,obj_name,mesh_path,texture_path,h,p,r):
        ShowBase.__init__(self)
        
        # Load the object model.
        self.loadObject(mesh_path,texture_path,h,p,r)
        # Needed for camera image
        self.dr = self.camNode.getDisplayRegion(0) 
        # Needed for camera depth image
        winprops = WindowProperties.size(self.win.getXSize(), self.win.getYSize())
        print(self.win.getXSize())
        fbprops = FrameBufferProperties()
        fbprops.setDepthBits(1)
        self.depthBuffer = self.graphicsEngine.makeOutput(
            self.pipe, "depth buffer", -2,
            fbprops, winprops,
            GraphicsPipe.BFRefuseWindow,
            self.win.getGsg(), self.win)
        self.depthTex = Texture()
        self.depthTex.setFormat(Texture.FDepthComponent)
        self.depthBuffer.addRenderTexture(self.depthTex,
            GraphicsOutput.RTMCopyRam, GraphicsOutput.RTPDepth)
        lens = self.cam.node().getLens()
        # the near and far clipping distances can be changed if desired
        # lens.setNear(5.0)
        lens.setFar(2.5)
        lens.setFov(40)

        self.camfx = 800*lens.getFocalLength()
        self.camfy = 800*lens.getFocalLength()

        self.depthCam = self.makeCamera(self.depthBuffer,
            lens=lens,
            scene=render)
        self.depthCam.reparentTo(self.cam)

        # TODO: Scene is rendered twice: once for rgb and once for depth image.
        # How can both images be obtained in one rendering pass?

    def loadObject(self,mesh_path,texture_path,h,p,r):
        # load mesh file
        self.testobj = self.loader.load_model(mesh_path)
        self.testobj.reparentTo(self.render)
        self.testobj.setScale(1, 1, 1)
        self.testobj.setPos(0,0, 0)

        self.testobj.setHpr(h,p,r)

        print(self.testobj.getTightBounds())
        # load and attach texture file
        tex = self.loader.loadTexture(texture_path)
        self.testobj.setTexture(tex)

        # set material
        myMaterial = Material()
        myMaterial.setDiffuse((1,1,1,1)) 
        myMaterial.setAmbient((1, 1, 1, 1)) 
        myMaterial.setRoughness(1)
        # myMaterial.setShininess(1)
        self.testobj.setMaterial(myMaterial) #Apply the material to this nodePath


    def get_camera_image(self, requested_format=None):
        """
        Returns the camera's image, which is of type uint8 and has values
        between 0 and 255.
        The 'requested_format' argument should specify in which order the
        components of the image must be. For example, valid format strings are
        "RGBA" and "BGRA". By default, Panda's internal format "BGRA" is used,
        in which case no data is copied over.
        """
        tex = self.dr.getScreenshot()
        if requested_format is None:
            data = tex.getRamImage()
        else:
            data = tex.getRamImageAs(requested_format)
        image = np.frombuffer(data, np.uint8)  
        image.shape = (tex.getYSize(), tex.getXSize(), tex.getNumComponents())
        image = np.flipud(image)
        return image

    def get_camera_depth_image(self):
        """
        Returns the camera's depth image, which is of type float32 and has
        values between 0.0 and 1.0.
        """
        data = self.depthTex.getRamImage()
        depth_image = np.frombuffer(data, np.float32)
        depth_image.shape = (self.depthTex.getYSize(), self.depthTex.getXSize(), self.depthTex.getNumComponents())
        depth_image = np.flipud(depth_image)
        return depth_image

    def save_camera_params(self,datadir,obj_name,img_name):
        cam_intrinsics = [self.camfx,0,400,0,self.camfy,300,0,0,1]
        #cam_intrinsics = [2,0,0,0,2.667,0,0,0,1]
        #cam_extrinsics_flat = list(self.cam_extrinsics.flatten())

        with open(datadir+obj_name+".csv","a",newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([img_name, cam_intrinsics])



def main(obj_name,objhprs):
        
    obj_height = 0.2
    mesh_path = "blendermodels\\"+obj_name+"\\textured.obj"
    texture_path = "blendermodels\\"+obj_name+"\\texture_map.png"


    h = objhprs[obj_name][0]
    p = objhprs[obj_name][1]
    r = objhprs[obj_name][2]
    
    app = MyApp(obj_name,mesh_path,texture_path,h,p,r)

    
    rootdatadir = './data/'
    cam_r = 1.5
    plight_r = 3
    datadir = rootdatadir+obj_name+'/'
    if not os.path.exists(datadir):
        os.makedirs(datadir)
    for cam_b_deg in range(0,185,5):
        print(cam_b_deg)
        if not os.path.exists(datadir+str(cam_b_deg)+'/'):
            os.makedirs(datadir+str(cam_b_deg)+'/')
        ndatadir = datadir+str(cam_b_deg)+'/'

        for cam_r_deg in [0]:
            if not os.path.exists(ndatadir+str(cam_r_deg)+'/'):
                os.makedirs(ndatadir+str(cam_r_deg)+'/')
            nndatadir = ndatadir+str(cam_r_deg)+'/'
            if not os.path.exists(nndatadir+'rgb/'):
                os.makedirs(nndatadir+'rgb/')

            if not os.path.exists(nndatadir+'depth/'):
                os.makedirs(nndatadir+'depth/')


            for cam_a_deg in range(0,365,5):
                t = time.time()
                cam_a_rad = cam_a_deg * (pi/180.0)
                cam_b_rad = cam_b_deg * (pi/180.0)


                cam_x = cam_r*sin(cam_b_rad)*sin(cam_a_rad)
                cam_y = -cam_r*sin(cam_b_rad)*cos(cam_a_rad)
                cam_z = cam_r*cos(cam_b_rad)
                #print(cam_x,cam_y,cam_z)
                app.camera.setPos(cam_x, cam_y, cam_z)
                cam_h = cam_a_deg
                cam_p =-90+cam_b_deg#-45 #-np.arctan2(cam_z-obj_height/2,cam_r*sin(cam_b_rad))/pi*180


                app.camera.setHpr(cam_h,cam_p,cam_r_deg) # in degrees

                app.graphicsEngine.renderFrame()
                image = app.get_camera_image()
                depth_image = app.get_camera_depth_image()
                save_rgbd_image(image, depth_image,nndatadir,str(cam_a_deg)+'.png',None,None)
                app.save_camera_params(nndatadir,obj_name,str(cam_a_deg)+'.png')


if __name__ == '__main__':
    objlist = ["004_sugar_box","006_mustard_bottle","009_gelatin_box","021_bleach_cleanser","035_power_drill","036_wood_block","054_softball","055_baseball",
    "005_tomato_soup_can","019_pitcher_base","003_cracker_box","008_pudding_box","007_tuna_fish_can","002_mast_chef_can",
    "071_nine_hole_peg_test","077_rubiks_cube","025_mug","056_tennis_ball","057_racquetball","058_golf_ball","053_mini_soccer_ball",
    "052_extra_large_clamp","051_large_clamp","061_foam_brick","073-b_lego_duplo","073-c_lego_duplo",
    'ice_cream',"001_chips_can",'hot_sauce',"010_potted_meat_can","043_phillips_screwdriver","061_foam_brick_new","048_hammer","037_scissors","031_spoon","038_padlock","029_plate","024_bowl","009_gelatin_box_new"]
    objhprs = {}
    objhprs["006_mustard_bottle"] = (23,0,0)
    objhprs["004_sugar_box"] = (90,0,0)
    objhprs["009_gelatin_box"] = (90,90-13,90)
    objhprs["021_bleach_cleanser"] = (0,0,0)
    objhprs["035_power_drill"] = (0,90,0)
    objhprs["036_wood_block"] = (13,0,0)
    objhprs["055_baseball"] = (0,0,0)
    objhprs["054_softball"] = (0,0,0)
    objhprs["005_tomato_soup_can"] = (0,0,0)
    objhprs["019_pitcher_base"] = (-45,0,0)
    objhprs["003_cracker_box"] = (90,0,0)
    objhprs["008_pudding_box"] = (90,-27,90)
    objhprs["007_tuna_fish_can"] = (0,90,0)
    objhprs["002_mast_chef_can"] = (0,0,0)
    objhprs["071_nine_hole_peg_test"] = (90,155,90)
    objhprs["077_rubiks_cube"] = (-30,0,0)
    objhprs["025_mug"] = (0,0,-90)
    objhprs["056_tennis_ball"] = (0,0,0)
    objhprs["057_racquetball"] = (0,0,0)
    objhprs["058_golf_ball"] = (0,0,0)
    objhprs["053_mini_soccer_ball"] = (0,0,0)
    objhprs["052_extra_large_clamp"] = (90,-7,90)
    objhprs["051_large_clamp"] = (85,-98, 80)
    objhprs["061_foam_brick"] = (0,90,0)
    objhprs["073-c_lego_duplo"] = (90,90,90)
    objhprs["073-b_lego_duplo"] = (-10,0,0) #b and f are same
    objhprs["ice_cream"] = (0,+90,0)
    objhprs["001_chips_can"] = (0,90,00) 
    objhprs["hot_sauce"] = (0,90,0)
    objhprs["010_potted_meat_can"] = (0,-2,90)
    objhprs["043_phillips_screwdriver"] = (0,90,0)
    objhprs["061_foam_brick_new"] = (0,0,90)
    objhprs["048_hammer"] = (0,90,0)
    objhprs["037_scissors"] = (0,-90,0)
    objhprs["031_spoon"] = (0,90,0)
    objhprs["038_padlock"] = (0,90,0)
    objhprs["029_plate"] = (0,90,0)
    objhprs["024_bowl"] = (0,90,0)
    objhprs["009_gelatin_box_new"] = (0,0,0)
    obj_name = objlist[-1]
    main(obj_name,objhprs)
 
 
