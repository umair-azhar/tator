import tempfile
import traceback
import logging
import os
import subprocess
import math
import io
from PIL import Image, ImageDraw, ImageFont
import textwrap

from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.generics import RetrieveUpdateDestroyAPIView
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied
from django.db.models import Case, When
from django.db import connection
from django.conf import settings

from ..models import EntityBase
from ..models import EntityMediaBase
from ..models import EntityMediaImage
from ..models import EntityMediaVideo
from ..serializers import EntityMediaSerializer
from ..search import TatorSearch
from ..renderers import JpegRenderer
from ..renderers import GifRenderer
from ..renderers import Mp4Renderer
from ..schema import MediaListSchema
from ..schema import MediaDetailSchema
from ..schema import GetFrameSchema
from ..schema import parse

from ._media_query import get_media_queryset
from ._attributes import AttributeFilterMixin
from ._attributes import bulk_patch_attributes
from ._attributes import patch_attributes
from ._attributes import validate_attributes
from ._util import delete_polymorphic_qs
from ._permissions import ProjectEditPermission
from ._permissions import ProjectViewOnlyPermission

logger = logging.getLogger(__name__)

class MediaListAPI(ListAPIView, AttributeFilterMixin):
    """ Interact with list of media.

        A media may be an image or a video. Media are a type of entity in Tator, 
        meaning they can be described by user defined attributes.

        This endpoint supports bulk patch of user-defined localization attributes and bulk delete.
        Both are accomplished using the same query parameters used for a GET request.

        This endpoint does not include a POST method. Creating media must be preceded by an
        upload, after which a separate media creation endpoint must be called. The media creation
        endpoints are `Transcode` to launch a transcode of an uploaded video and `SaveImage` to
        save an uploaded image. If you would like to perform transcodes on local assets, you can
        use the `SaveVideo` endpoint to save an already transcoded video. Local transcodes may be
        performed with the script at `scripts/transcoder/transcodePipeline.py` in the Tator source
        code.
    """
    schema = MediaListSchema()
    serializer_class = EntityMediaSerializer
    permission_classes = [ProjectEditPermission]

    def get(self, request, *args, **kwargs):
        try:
            params = parse(request)
            self.validate_attribute_filter(params)
            media_ids, media_count, _ = get_media_queryset(
                self.kwargs['project'],
                params,
            )
            if len(media_ids) > 0:
                preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(media_ids)])
                qs = EntityMediaBase.objects.filter(pk__in=media_ids).order_by(preserved)
                # We are doing a full query; so we should bypass the ORM and
                # use the SQL cursor directly.
                # TODO: See if we can do this using queryset into a custom serializer instead
                # of naked SQL.
                original_sql,params = qs.query.sql_with_params()
                root_url = request.build_absolute_uri("/").strip("/")
                media_url = request.build_absolute_uri(settings.MEDIA_URL)
                raw_url = request.build_absolute_uri(settings.RAW_ROOT)
                # Modify original sql to have aliases to match JSON output
                original_sql = original_sql.replace('"main_entitybase"."id,"', '"main_entitybase"."id" AS id,',1)
                original_sql = original_sql.replace('"main_entitybase"."polymorphic_ctype_id",', '',1)
                original_sql = original_sql.replace('"main_entitybase"."project_id",', '"main_entitybase"."project_id" AS project,',1)
                original_sql = original_sql.replace('"main_entitybase"."meta_id",', '"main_entitybase"."meta_id" AS meta,',1)
                original_sql = original_sql.replace('"main_entitymediabase"."file",', f'CONCAT(\'{media_url}\',"main_entitymediabase"."file") AS url,',1)

                new_selections =  f'NULLIF(CONCAT(\'{media_url}\',"main_entitymediavideo"."thumbnail"),\'{media_url}\') AS video_thumbnail'
                new_selections += f', NULLIF(CONCAT(\'{media_url}\',"main_entitymediaimage"."thumbnail"),\'{media_url}\') AS image_thumbnail'
                new_selections += f', NULLIF(CONCAT(\'{media_url}\',"main_entitymediavideo"."thumbnail_gif"),\'{media_url}\') AS video_thumbnail_gif'
                new_selections += f', NULLIF(CONCAT(\'{root_url}\',"main_entitymediavideo"."original"),\'{root_url}\') AS original_url'
                new_selections += f', "main_entitymediavideo"."media_files" AS media_files'
                original_sql = original_sql.replace(" FROM ", f",{new_selections} FROM ",1)

                #Add new joins
                new_joins = f'LEFT JOIN "main_entitymediaimage" ON ("main_entitymediabase"."entitybase_ptr_id" = "main_entitymediaimage"."entitymediabase_ptr_id")'
                new_joins += f' LEFT JOIN "main_entitymediavideo" ON ("main_entitymediabase"."entitybase_ptr_id" = "main_entitymediavideo"."entitymediabase_ptr_id")'
                original_sql = original_sql.replace(" INNER JOIN ", f" {new_joins} INNER JOIN ",1)

                # Generate JSON serialization string
                json_sql = f"SELECT json_agg(r) FROM ({original_sql}) r"
                logger.info(json_sql)

                with connection.cursor() as cursor:
                    cursor.execute(json_sql,params)
                    result = cursor.fetchone()
                    responseData=result[0]
                    if responseData is None:
                        responseData=[]
            else:
                responseData = []
        except Exception as e:
            logger.error(traceback.format_exc())
            response=Response({'message' : str(e),
                               'details': traceback.format_exc()}, status=status.HTTP_400_BAD_REQUEST)
            return response;

        return Response(responseData)

    def get_queryset(self):
        params = parse(self.request)
        media_ids, media_count, _ = get_media_queryset(
            params['project'],
            params,
        )
        queryset = EntityMediaBase.objects.filter(pk__in=media_ids).order_by('name')
        return queryset

    def delete(self, request, **kwargs):
        response = Response({})
        try:
            params = parse(request)
            self.validate_attribute_filter(params)
            media_ids, media_count, query = get_media_queryset(
                params['project'],
                params,
            )
            if len(media_ids) == 0:
                raise ObjectDoesNotExist
            qs = EntityBase.objects.filter(pk__in=media_ids)
            delete_polymorphic_qs(qs)
            TatorSearch().delete(self.kwargs['project'], query)
            response=Response({'message': 'Batch delete successful!'},
                              status=status.HTTP_204_NO_CONTENT)
        except ObjectDoesNotExist as dne:
            response=Response({'message' : str(dne)},
                              status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            response=Response({'message' : str(e),
                               'details': traceback.format_exc()}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            return response;

    def patch(self, request, **kwargs):
        response = Response({})
        try:
            params = parse(request)
            self.validate_attribute_filter(params)
            media_ids, media_count, query = get_media_queryset(
                params['project'],
                params,
            )
            if len(media_ids) == 0:
                raise ObjectDoesNotExist
            qs = EntityBase.objects.filter(pk__in=media_ids)
            new_attrs = validate_attributes(request, qs[0])
            bulk_patch_attributes(new_attrs, qs)
            TatorSearch().update(self.kwargs['project'], query, new_attrs)
            response=Response({'message': 'Attribute patch successful!'},
                              status=status.HTTP_200_OK)
        except ObjectDoesNotExist as dne:
            response=Response({'message' : str(dne)},
                              status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            response=Response({'message' : str(e),
                               'details': traceback.format_exc()}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            return response;

class MediaUtil:
    def __init__(self, video, temp_dir):
        self._temp_dir = temp_dir

        if video.file:
            video_file = video.file.path
            self._height = video.height
            self._width = video.width
            # Make file relative to URL to be consistent with streaming files below
            video_file = os.path.relpath(video_file, settings.MEDIA_ROOT)
            self._video_file = os.path.join(settings.MEDIA_URL, video_file)
        else:
            self._video_file = video.media_files["streaming"][0]["path"]
            self._height = video.media_files["streaming"][0]["resolution"][0]
            self._width = video.media_files["streaming"][0]["resolution"][1]

        self._video_file = os.path.relpath(self._video_file, settings.MEDIA_URL)
        self._video_file = os.path.join(settings.MEDIA_ROOT, self._video_file)

        self._fps = video.fps

    def frameToTimeStr(self, frame):
        total_seconds = int(frame) / self._fps
        hours = math.floor(total_seconds / 3600)
        minutes = math.floor((total_seconds % 3600) / 60)
        seconds = total_seconds % 60
        return f"{hours}:{minutes}:{seconds}"

    def _generateFrameImages(self, frames, rois=None):
        crop_filter = None
        if rois:
            crop_filter = [f"crop={round(c[0]*self._width)}:{round(c[1]*self._height)}:{round(c[2]*self._width)}:{round(c[3]*self._height)}" for c in rois]

        logger.info(f"Processing {self._video_file}")
        args = ["ffmpeg"]
        inputs = []
        outputs = []
        for frame_idx,frame in enumerate(frames):
            outputs.extend(["-map", f"{frame_idx}:v","-frames:v", "1", "-q:v", "3"])
            if crop_filter:
                outputs.extend(["-vf", crop_filter[frame_idx]])

            outputs.append(os.path.join(self._temp_dir,f"{frame_idx}.jpg"))
            inputs.extend(["-ss", self.frameToTimeStr(frame), "-i", self._video_file])

        # Now add all the cmds in
        args.extend(inputs)
        args.extend(outputs)
        proc = subprocess.run(args, check=True, capture_output=True)
        return proc.returncode == 0

    def getTileImage(self, frames, rois=None, tile_size=None):
        """ Generate a tile jpeg of the given frame/rois """
        # Compute tile size if not supplied explicitly
        try:
            if tile_size != None:
                # check supplied tile size makes sense
                comps=tile_size.split('x')
                if len(comps) != 2:
                    raise Exception("Bad Tile Size")
                if int(comps[0])*int(comps[1]) < len(frames):
                    raise Exception("Bad Tile Size")
        except:
            tile_size = None
            # compute the required tile size
        if tile_size == None:
            width = math.ceil(math.sqrt(len(frames)))
            height = math.ceil(len(frames) / width)
            tile_size = f"{width}x{height}"

        if self._generateFrameImages(frames, rois) == False:
            return None

        output_file = None
        if len(frames) > 1:
            # Make a tiled jpeg
            tile_args = ["ffmpeg",
                         "-i", os.path.join(self._temp_dir, f"%d.jpg"),
                         "-vf", f"tile={tile_size}",
                         "-q:v", "3",
                         os.path.join(self._temp_dir,"tile.jpg")]
            logger.info(tile_args)
            proc = subprocess.run(tile_args, check=True, capture_output=True)
            if proc.returncode == 0:
                output_file = os.path.join(self._temp_dir,"tile.jpg")
        else:
            output_file = os.path.join(self._temp_dir,f"0.jpg")

        return output_file

    def getAnimation(self,frames, roi, fps, render_format):
        if self._generateFrameImages(frames, roi) == False:
            return None

        mp4_args = ["ffmpeg",
                    "-framerate", str(fps),
                    "-i", os.path.join(self._temp_dir, f"%d.jpg"),
                    os.path.join(self._temp_dir, "temp.mp4")]
        proc = subprocess.run(mp4_args, check=True, capture_output=True)

        if render_format == 'mp4':
            return os.path.join(self._temp_dir, "temp.mp4")
        else:
            # Convert temporary mp4 into a gif
            gif_args = ["ffmpeg",
                        "-i", os.path.join(self._temp_dir, "temp.mp4"),
                        "-filter_complex", f"[0:v] split [a][b];[a] palettegen [p];[b][p] paletteuse",
                        os.path.join(self._temp_dir,"animation.gif")]
            logger.info(gif_args)
            proc = subprocess.run(gif_args, check=True, capture_output=True)
            return os.path.join(self._temp_dir,"animation.gif")

    def generate_error_image(code, message):
        font_bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 32)
        font = ImageFont.truetype("DejaVuSans.ttf", 28)
        img = Image.open(os.path.join(settings.STATIC_ROOT,
                                      "images/computer.jpg"))
        draw = ImageDraw.Draw(img)
        W, H = img.size

        x_bias = 60
        header=f"Error {code}"
        w, h = draw.textsize(header)
        logger.info(f"{W}-{w}/2; {H}-{h}/2")
        offset = font.getoffset(header)
        logger.info(f"Offset = {offset}")

        draw.text((W/2-((w/2)+x_bias),80), header, (255,62,29), font=font_bold)


        _, line_height = draw.textsize(message)
        line_height *= 3
        start_height = 200-line_height
        lines = textwrap.wrap(message,17)
        for line_idx, line in enumerate(lines):
            draw.text((100,start_height+(line_height*line_idx)), line, (255,62,29), font=font)

        img_buf = io.BytesIO()
        img.save(img_buf, "jpeg", quality=95)
        return img_buf.getvalue()

class MediaDetailAPI(RetrieveUpdateDestroyAPIView):
    """ Interact with individual media.

        A media may be an image or a video. Media are a type of entity in Tator, 
        meaning they can be described by user defined attributes.
    """
    schema = MediaDetailSchema()
    serializer_class = EntityMediaSerializer
    queryset = EntityMediaBase.objects.all()
    permission_classes = [ProjectEditPermission]
    lookup_field = 'id'

    def patch(self, request, **kwargs):
        response = Response({})
        try:
            params = parse(request)
            media_object = EntityMediaBase.objects.get(pk=params['id'])
            if 'attributes' in params:
                self.check_object_permissions(request, media_object)
                new_attrs = validate_attributes(request, media_object)
                patch_attributes(new_attrs, media_object)

                if type(media_object) == EntityMediaImage:
                    for localization in media_object.thumbnail_image.all():
                        patch_attributes(new_attrs, localization)
            if 'media_files' in params:
                # TODO: for now just pass through, eventually check URL
                media_object.media_files = params['media_files']
                logger.info(f"Media files = {media_object.media_files}")

            if 'name' in params:
                media_object.name = params['name']

            if 'last_edit_start' in params:
                media_object.last_edit_start = params['last_edit_start']

            if 'last_edit_end' in params:
                media_object.last_edit_end = params['last_edit_end']

            media_object.save()
                
        except PermissionDenied as err:
            raise
        except ObjectDoesNotExist as dne:
            response=Response({'message' : str(dne)},
                              status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            response=Response({'message' : str(e),
                               'details': traceback.format_exc()}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            return response;

class GetFrameAPI(APIView):
    schema = GetFrameSchema()
    renderer_classes = (JpegRenderer,)
    renderer_classes = (JpegRenderer, GifRenderer, Mp4Renderer)
    permission_classes = [ProjectViewOnlyPermission]

    def get_queryset(self):
        return EntityBase.objects.all()

    def get(self, request, **kwargs):
        """ Facility to get a frame(jpg/png) of a given video frame, returns a square tile of 
            frames based on the input parameter
        """
        try:
            # upon success we can return an image
            params = parse(request)
            video = EntityMediaVideo.objects.get(pk=params['id'])
            frames = params.get('frames', '0')

            if len(frames) > 32:
                raise Exception("Too many frames requested (Max = 32)")

            for frame in frames:
                if int(frame) >= video.num_frames:
                    raise Exception(f"Frame {frame} is invalid. Maximum frame is {video.num_frames-1}")
                elif int(frame) < 0:
                    raise Exception(f"Frame {frame} is invalid. Must be greater than 0.")
            tile_size = params.get('tile', None)

            if values['tile'] and values['animate']:
                raise Exception("Can't supply both tile and animate arguments")

            if values['animate']:
                if values['animate'].isdecimal() is False:
                    raise Exception('Animation FPS must be an integer')
                if int(values['animate']) > 15 or int(values['animate']) <= 0:
                    raise Exception('Animation FPS must be between >0 and <=15')


            # compute the crop argument
            roi_arg = []
            roi = params.get('roi', None)
            if roi:
                crop_filter = [None] * len(frames)
                roi_list = roi.split(',')
                logger.info(roi_list)
                if len(roi_list) == 1:
                    # Repeat the same roi if only 1 is given for a set
                    comps = roi_list[0].split(':')
                    if len(comps) == 4:
                        box_width = float(comps[0])
                        box_height = float(comps[1])
                        x = float(comps[2])
                        y = float(comps[3])
                        roi_arg = [(box_width,box_height,x,y)]*len(frames)
                else:
                    # If each individual roi is supplied manually set each one
                    if len(roi_list) != len(frames):
                        raise Exception(f'Explicit roi list{len(roi_list)} is different length than frame list{len(frames)}')
                    for idx,frame_roi in enumerate(roi_list):
                        comps = frame_roi.split(':')
                        if len(comps) == 4:
                            box_width = float(comps[0])
                            box_height = float(comps[1])
                            x = float(comps[2])
                            y = float(comps[3])
                            roi_arg.append((box_width,box_height,x,y))



            with tempfile.TemporaryDirectory() as temp_dir:
                media_util = MediaUtil(video, temp_dir)
                if len(frames) > 1 and values['animate']:
                    # Default to gif for animate, but mp4 is also supported
                    if any(x is request.accepted_renderer.format for x in ['mp4','gif']):
                        pass
                    else:
                        request.accepted_renderer = GifRenderer()
                    gif_fp = media_util.getAnimation(frames, roi_arg, fps=values['animate'], render_format=request.accepted_renderer.format)
                    with open(gif_fp, 'rb') as data_file:
                        response = Response(data_file.read())
                else:
                    tiled_fp = media_util.getTileImage(frames, roi_arg, tile_size)
                    with open(tiled_fp, 'rb') as data_file:
                        response = Response(data_file.read())


        except ObjectDoesNotExist as dne:
            response=Response(MediaUtil.generate_error_image(404, "No Media Found"),
                              status=status.HTTP_404_NOT_FOUND)
            logger.warning(traceback.format_exc())
        except Exception as e:
            response=Response(MediaUtil.generate_error_image(400, str(e)),
                              status=status.HTTP_400_BAD_REQUEST)
            logger.warning(traceback.format_exc())
        finally:
            return response
