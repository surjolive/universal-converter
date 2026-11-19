from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import DATABASE

DATABASE_URL = f"sqlite:///{DATABASE / 'converter.db'}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

class Conversion(Base):
    __tablename__ = "conversions"
    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String(255), nullable=False)
    source_format = Column(String(20), nullable=False)
    target_format = Column(String(20), nullable=False)
    file_size = Column(Float, default=0)
    output_size = Column(Float, default=0)
    status = Column(String(20), nullable=False)
    conversion_time = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    error = Column(Text, default="")
    engine = Column(String(50), default="")
    output_path = Column(Text, default="")

Base.metadata.create_all(bind=engine)
