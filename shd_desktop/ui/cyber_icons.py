"""Crisp, angular monochrome category symbols for yellow Cyberpunk headers."""
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF


def category_pixmap(title: str, source: str, size=25, color="#111214"):
    from shd_desktop.resources import ASSETS
    atlas = QPixmap(str(ASSETS / 'cyberpunk' / 'icons-atlas.png'))
    key = (title + ' ' + source).lower()
    if not atlas.isNull():
        index = 1
        for words, candidate in [
            (('工具','tool','logistics'),0), (('game','游戏','combat'),2),
            (('文档','document','intel'),3), (('clock','briefing','日程','委托'),4),
            (('widgets','便签','备忘'),5), (('天气','气象','weather'),6),
            (('media','音乐','电台','视频','图片'),7), (('isac','银手','johnny'),8),
            (('system','settings','配置'),9), (('search','查找','扫描'),10), (('power','退出'),11)]:
            if any(word in key for word in words):
                index = candidate
                break
        row, col = divmod(index,4)
        top, bottom = [(130,445),(470,810),(815,1165)][row]
        tile = atlas.copy(col*320, top, 320, bottom-top)
        result = tile.scaled(size*2,size*2,Qt.KeepAspectRatio,Qt.SmoothTransformation)
        result.setDevicePixelRatio(2)
        return result
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / 24, size / 24)
    painter.setPen(QPen(QColor(color), 1.8, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
    painter.setBrush(Qt.NoBrush)

    def lines(points):
        painter.drawPolyline(QPolygonF([QPointF(*p) for p in points]))

    key = (title + ' ' + source).lower()
    if any(word in key for word in ('game', '游戏', 'combat')):
        lines([(3,7),(7,4),(17,4),(21,7),(22,18),(18,20),(14,16),(10,16),(6,20),(2,18),(3,7)])
        painter.drawLine(5,10,11,10)
        painter.drawLine(8,7,8,13)
        painter.drawRect(16,8,2,2)
        painter.drawRect(18,12,2,2)
    elif any(word in key for word in ('clock', 'briefing', '日程')):
        lines([(5,2),(19,2),(22,5),(22,19),(19,22),(5,22),(2,19),(2,5),(5,2)])
        lines([(12,5),(12,12),(17,15)])
    elif any(word in key for word in ('isac', '银手')):
        lines([(5,3),(19,3),(22,7),(22,17),(18,21),(6,21),(2,17),(2,7),(5,3)])
        lines([(7,8),(10,8),(10,15),(6,15)])
        lines([(18,8),(14,8),(14,12),(18,12),(18,16),(14,16)])
    elif any(word in key for word in ('工具', 'tool', 'system', 'logistics')):
        lines([(14,3),(19,3),(16,6),(18,9),(21,6),(21,11),(17,14),(13,13),(6,21),(3,18),(11,10),(10,6),(14,3)])
    elif any(word in key for word in ('文档', 'intel', 'document')):
        lines([(5,2),(15,2),(20,7),(20,22),(5,22),(5,2)])
        lines([(15,2),(15,7),(20,7)])
        painter.drawLine(8,11,16,11)
        painter.drawLine(8,15,16,15)
        painter.drawLine(8,19,13,19)
    elif any(word in key for word in ('media', '音乐', '视频', '图片')):
        lines([(3,5),(17,5),(21,9),(21,20),(3,20),(3,5)])
        lines([(9,9),(15,13),(9,17),(9,9)])
    else:
        for x,y in ((3,3),(14,3),(3,14),(14,14)):
            lines([(x,y),(x+5,y),(x+7,y+2),(x+7,y+7),(x,y+7),(x,y)])
    painter.end()
    return pixmap
