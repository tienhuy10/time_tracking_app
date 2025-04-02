import tkinter as tk
app = tk.Tk()
app.title("Ứng dụng")
app.geometry("800x500")



text_vitri = "Nghệ An là tỉnh nằm ở vị trí trung tâm vùng Bắc Trung Bộ, là địa phương có lịch sử hình thành và phát triển lâu đời, giàu truyền thống cách mạng và tinh thần hiếu học. Nghệ An còn là mảnh đất đã sản sinh nhiều anh hùng, hào kiệt, danh tướng, danh nhân lịch sử cho đất nước. Đặc biệt, Nghệ An là quê hương của Chủ tịch Hồ Chí Minh, vị lãnh tụ vĩ đại của dân tộc Việt Nam, anh hùng giải phóng dân tộc, danh nhân văn hóa thế giới."
text_vanhoa = "Nghệ An có nhiều di sản văn hóa vật thể và phi vật thể phong phú, đa dạng. Trong đó có các di sản văn hóa phi vật thể như: Dân ca ví, giặm Nghệ Tĩnh, Nghệ An là nơi có nhiều lễ hội truyền thống đặc sắc như lễ hội đền Cuông, lễ hội đền Vạn Lộc, lễ hội đền Hồng Sơn..."
text_lichsu = "Nghệ An có nhiều di tích lịch sử văn hóa nổi tiếng như: Di tích lịch sử Quốc gia đặc biệt Kim Liên, di tích lịch sử Quốc gia đặc biệt Đền Cuông, di tích lịch sử Quốc gia đặc biệt Đền Hồng Sơn..."
text_dacsan = "Nghệ An nổi tiếng với nhiều món ăn đặc sản như: Bánh mướt, bánh đa, bánh cuốn, chè xanh, chè đậu xanh..."


label_vitri = tk.Label(app, text= text_vitri, font=("Arial", 16), wraplength=700, justify="left")
label_vitri.pack(pady=1)

label_vanhoa = tk.Label(app, text= text_vanhoa, font=("Arial", 16), wraplength=700, justify="left")
label_vanhoa.pack(pady=1)

label_lichsu = tk.Label(app, text= text_lichsu, font=("Arial", 16), wraplength=700, justify="left")
label_lichsu.pack(pady=1)

label_dacsan = tk.Label(app, text= text_dacsan, font=("Arial", 16), wraplength=700, justify="left")
label_dacsan.pack(pady=1)

img = tk.PhotoImage(file=r"D:\\time_tracking_app\\lap_trinh_vien_1.png")
label_img = tk.Label(app, image=img)
label_img.pack(pady=10)

app.mainloop()